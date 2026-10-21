"""Second-order spatial hierarchy for the actual affine tetrahedron current.

Near interactions retain exact exterior tetrahedron integration. Far moments
are integrated from the same finite cells, including RT0 radial terms, not a
wire approximation. Opening angle and leaf size are numerical resource controls.
This approximation has no claimed a-priori physical error bar: tighter-opening
and independent direct-source checks are required for each use/observation set.
"""
from dataclasses import dataclass
import time

import numpy as np

from finite_tetra_current_field import tetrahedron_field, MU0_OVER_4PI


def antisymmetric(matrix):
    return np.stack([matrix[..., 1, 2]-matrix[..., 2, 1], matrix[..., 2, 0]-matrix[..., 0, 2],
                     matrix[..., 0, 1]-matrix[..., 1, 0]], axis=-1)


@dataclass(slots=True)
class Node:
    centre: np.ndarray
    radius: float
    w: np.ndarray
    q: np.ndarray
    t: np.ndarray
    children: tuple
    cells: object


def leaf_moments(cells, mean, slope, volume, centre):
    centres = cells.mean(axis=1)
    offset = centres-centre
    deviations = cells-centres[:, None, :]
    covariance = np.einsum('nva,nvb->nab', deviations, deviations)/20
    third = np.einsum('nva,nvb,nvc->nabc', deviations, deviations, deviations)/60
    w = np.sum(mean*volume[:, None], axis=0)
    q = np.sum(volume[:, None, None]*(np.einsum('na,nb->nab', mean, offset)+slope[:, None, None]*covariance), axis=0)
    second_position = np.einsum('nb,nc->nbc', offset, offset)+covariance
    radial = offset[:, None, :, None]*covariance[:, :, None, :]+offset[:, None, None, :]*covariance[:, :, :, None]+third
    t = np.sum(volume[:, None, None, None]*(mean[:, :, None, None]*second_position[:, None, :, :]+slope[:, None, None, None]*radial), axis=0)
    return w, q, t


def shifted_moments(node, centre):
    offset = node.centre-centre
    q = node.q+np.outer(node.w, offset)
    t = (node.t+node.q[:, :, None]*offset[None, None, :]+node.q[:, None, :]*offset[None, :, None]
         +node.w[:, None, None]*offset[None, :, None]*offset[None, None, :])
    return node.w, q, t


def moment_field(points, node):
    delta = points-node.centre
    r2 = np.einsum('pi,pi->p', delta, delta)
    if np.any(r2 <= node.radius**2):
        raise ValueError('Far expansion evaluated within its source-support ball')
    inverse3 = r2**-1.5
    inverse5 = inverse3/r2
    inverse7 = inverse5/r2
    qr = np.einsum('ab,pb->pa', node.q, delta)
    tr = np.einsum('abc,pc->pab', node.t, delta)
    trr = np.einsum('abc,pb,pc->pa', node.t, delta, delta)
    trace = np.trace(node.t, axis1=1, axis2=2)
    result = (np.cross(node.w, delta)-antisymmetric(node.q))*inverse3[:, None]
    result += 3*np.cross(qr, delta)*inverse5[:, None]
    result += (-3*antisymmetric(tr)-1.5*np.cross(trace, delta))*inverse5[:, None]
    result += 7.5*np.cross(trr, delta)*inverse7[:, None]
    return MU0_OVER_4PI*result


class FiniteCurrentTree:
    def __init__(self, tetrahedra, mean_current, radial_slope=None, leaf_size=64):
        started = time.monotonic()
        self.cells = np.array(tetrahedra, dtype=float, copy=True)
        self.mean = np.array(mean_current, dtype=float, copy=True)
        self.slope = np.zeros(len(self.cells)) if radial_slope is None else np.array(radial_slope, dtype=float, copy=True)
        if self.cells.ndim != 3 or self.cells.shape[1:] != (4, 3) or self.mean.shape != (len(self.cells), 3) or self.slope.shape != (len(self.cells),) or not len(self.cells):
            raise ValueError('Actual affine tetrahedron/current arrays required')
        if type(leaf_size) is not int or leaf_size < 1 or not all(np.isfinite(x).all() for x in [self.cells, self.mean, self.slope]):
            raise ValueError('Finite source data and positive integral leaf size required')
        self.volume = abs(np.linalg.det(self.cells[:, 1:]-self.cells[:, :1]))/6
        if np.any(self.volume <= 0):
            raise ValueError('Degenerate source tetrahedron')
        self.centres = self.cells.mean(axis=1)
        self.lower, self.upper = self.cells.min(axis=1), self.cells.max(axis=1)
        self.leaf_size = leaf_size
        self.nodes = []
        self.root = self._build(np.arange(len(self.cells)))
        self.metadata = {'cells': len(self.cells), 'nodes': len(self.nodes), 'leaf_size': leaf_size,
                         'multipole_degree': 2, 'build_seconds': time.monotonic()-started,
                         'scope': 'Finite-cell source hierarchy, not a fitted physical correction or certified error bound'}

    def _build(self, indices):
        low, high = self.lower[indices].min(axis=0), self.upper[indices].max(axis=0)
        centre, radius = (low+high)/2, float(np.linalg.norm(high-low)/2)
        index = len(self.nodes)
        self.nodes.append(None)
        if len(indices) <= self.leaf_size:
            w, q, t = leaf_moments(self.cells[indices], self.mean[indices], self.slope[indices], self.volume[indices], centre)
            node = Node(centre, radius, w, q, t, (), indices)
        else:
            axis = int(np.argmax(np.ptp(self.centres[indices], axis=0)))
            middle = len(indices)//2
            order = np.argpartition(self.centres[indices, axis], middle)
            children = (self._build(indices[order[:middle]]), self._build(indices[order[middle:]]))
            w, q, t = np.zeros(3), np.zeros((3, 3)), np.zeros((3, 3, 3))
            for child in children:
                a, b, c = shifted_moments(self.nodes[child], centre)
                w += a
                q += b
                t += c
            node = Node(centre, radius, w, q, t, children, None)
        self.nodes[index] = node
        return index

    def field(self, points, opening=.25):
        started = time.monotonic()
        points = np.asarray(points, dtype=float)
        if points.ndim != 2 or points.shape[1:] != (3,) or not np.isfinite(points).all() or not np.isfinite(opening) or not 0 <= opening < 1:
            raise ValueError('Finite observations and opening ratio in[0,1) required')
        result = np.zeros_like(points)
        stack = [(self.root, np.arange(len(points)))]
        accepted, exact_pairs = 0, 0
        while stack:
            index, selected = stack.pop()
            if not len(selected):
                continue
            node = self.nodes[index]
            distances = np.linalg.norm(points[selected]-node.centre, axis=1)
            far = (distances > node.radius) & (node.radius < opening*distances)
            if np.any(far):
                result[selected[far]] += moment_field(points[selected[far]], node)
                accepted += int(far.sum())
            near = selected[~far]
            if not len(near):
                continue
            if node.children:
                for child in node.children:
                    stack.append((child, near))
            else:
                result[near] += tetrahedron_field(points[near], self.cells[node.cells], self.mean[node.cells], radial_slope=self.slope[node.cells])
                exact_pairs += len(near)*len(node.cells)
        if not np.isfinite(result).all():
            raise ValueError('Nonfinite hierarchical field')
        self.last_evaluation = {'opening': opening, 'points': len(points), 'far_point_nodes': accepted,
                                'exact_point_cell_pairs': exact_pairs, 'seconds': time.monotonic()-started,
                                'error_claim': 'None without tighter-opening and direct-reference controls'}
        return result
