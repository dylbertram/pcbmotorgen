"""Interpolate serial ASCII VTU vectors or raw Gmsh VS air fields on tetrahedra.

Deliberately rejects unsupported output instead of guessing binary/compressed
data or cell order. Used by offline Elmer checks, not by the application.
"""
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
import re

import numpy as np
from scipy.spatial import cKDTree


def values(array):
    if array.get("format", "ascii") != "ascii":
        raise ValueError("Expected ASCII VTU; set Binary Output = False")
    kind = array.get("type", "Float64")
    return np.fromstring(array.text or "", sep=" ", dtype=np.int64 if "Int" in kind else float)


def _read_vtu(path, name):
    root = ET.parse(path).getroot()
    pieces = root.findall("./UnstructuredGrid/Piece")
    if len(pieces) != 1:
        raise ValueError("Expected one serial VTU piece")
    piece = pieces[0]
    points = values(piece.find("./Points/DataArray")).reshape(-1, 3)
    arrays = {a.get("Name", "").casefold().replace("_", " "): a for a in piece.findall("./PointData/DataArray")}
    cell_arrays = {a.get("Name", "").casefold().replace("_", " "): a for a in piece.findall("./CellData/DataArray")}
    key = name.casefold().replace("_", " ")
    cells = {a.get("Name"): values(a) for a in piece.findall("./Cells/DataArray")}
    offsets = np.r_[0, cells["offsets"]]
    tetra = np.array([cells["connectivity"][offsets[i]:offsets[i+1]]
                      for i, kind in enumerate(cells["types"]) if kind == 10])
    if tetra.ndim != 2 or tetra.shape[1] != 4:
        raise ValueError("Expected linear tetrahedra")
    if key in arrays:
        field = values(arrays[key]).reshape(-1, 3)
        if field.shape != points.shape or not np.all(np.isfinite(field)):
            raise ValueError("Invalid VTU point field")
        vectors=field[tetra]
    elif key in cell_arrays:
        field=values(cell_arrays[key]).reshape(-1,3)
        if field.shape != (len(cells['types']),3) or not np.isfinite(field).all():
            raise ValueError('Invalid VTU cell vector field')
        vectors=np.repeat(field[cells['types']==10,None,:],4,axis=1)
    else:
        raise ValueError(f"Missing {name}, available fields: {list(arrays)+list(cell_arrays)}")
    return points[tetra],vectors


@lru_cache(maxsize=2)
def _vector_mesh(path, modified_ns, size, name):
    if Path(path).suffix=='.pos':
        entries=re.findall(r'VS\(([^)]+)\)\{([^}]+)\};',Path(path).read_text())
        if not entries:
            raise ValueError('Expected vector tetrahedra in ASCII Gmsh output')
        data=np.array([np.fromstring(coords+','+field,sep=',') for coords,field in entries])
        if data.shape[1]!=24 or not np.isfinite(data).all():
            raise ValueError('Expected four coordinates and four vectors per tetrahedron')
        vertices=data[:,:12].reshape(-1,4,3)
        fields=data[:,12:].reshape(-1,4,3)
    else:
        vertices,fields=_read_vtu(path,name)
    lo, hi = vertices.min(axis=1), vertices.max(axis=1)
    centres=vertices.mean(axis=1)
    radii=np.linalg.norm(vertices-centres[:,None,:],axis=2).max(axis=1)
    buckets=[]
    levels=np.floor(np.log2(radii)).astype(int)
    for level in np.unique(levels):
        indices=np.flatnonzero(levels==level)
        buckets.append((indices,cKDTree(centres[indices]),radii[indices].max()+1e-12))
    return vertices,fields,lo,hi,buckets


def sample_vector(path, observations, name="magnetic flux density"):
    path=Path(path)
    stat=path.stat()
    vertices,fields,lo,hi,buckets=_vector_mesh(str(path.resolve()),stat.st_mtime_ns,stat.st_size,name)
    observations=np.asarray(observations)
    candidates=[[] for _ in observations]
    for indices,tree,radius in buckets:
        for found,nearby in zip(candidates,tree.query_ball_point(observations,radius)):
            found.extend(indices[nearby])
    sampled = []
    for point,candidate in zip(observations,candidates):
        candidate=np.asarray(candidate,dtype=int)
        candidate=candidate[np.all(point>=lo[candidate]-1e-12,axis=1)&np.all(point<=hi[candidate]+1e-12,axis=1)]
        found = []
        for i in candidate:
            v = vertices[i]
            xyz = np.linalg.solve((v[1:] - v[0]).T, point - v[0])
            barycentric = np.r_[1 - xyz.sum(), xyz]
            if barycentric.min() >= -1e-9 and barycentric.max() <= 1 + 1e-9:
                found.append(barycentric @ fields[i])
        if not found:
            raise ValueError(f"Observation outside the tetrahedral mesh: {point}")
        sampled.append(np.mean(found, axis=0))
    return np.array(sampled)


def clear_vector_cache():
    """Release large completed-case fields before starting another solver."""
    _vector_mesh.cache_clear()
