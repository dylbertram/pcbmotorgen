"""Inspect the revised DXFs without regenerating or repairing their copper.

The only diagnostic transformation assigns each net-0 series barrel to the
unique phase at its actual trace landings. Original connectivity and source
bytes are retained in the receipt. No missing trace is bridged. Current signs
come from an independent resistor solve on raw DXF endpoints, snapped to the
same declared 1 um connection grid as the native solver.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np

from audit_compact_spread_dxf import raw_edges, key, sha
from winding_oracle import unit_currents


def graph(edges, net, star):
    es = [(key(a), key(b), np.linalg.norm(np.subtract(b, a)))
          for name, a, b in edges if name == net]
    nodes = sorted({p for a, b, _ in es for p in (a, b)})
    indices = {p: i for i, p in enumerate(nodes)}
    adjacency = defaultdict(set)
    for a, b, _ in es:
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen, pending = set(), [nodes[0]]
    while pending:
        p = pending.pop()
        if p not in seen:
            seen.add(p)
            pending.extend(adjacency[p])
    connected = len(seen) == len(nodes)
    ends = [p for p in nodes if len(adjacency[p]) == 1]
    receipt = dict(connected=connected, nodes=len(nodes), edges=len(es),
                   cycles=len(es)-len(nodes)+1,
                   degree_one_xyz_mm=[[v/1000 for v in p] for p in ends])
    if not connected:
        return receipt, {}
    drivers = [p for p in ends if p[0] == 0 and p[2] == 0 and p[1] > 8000]
    assert len(drivers) == 1
    driver = drivers[0]
    assert set(ends) == {driver, star}, 'Do not infer fictitious terminal buses'
    network = dict(node_count=len(nodes), terminal=[indices[driver]], star=[indices[star]],
                   edges=[dict(a=indices[a], b=indices[b]) for a, b, _ in es])
    # Explicit uniform 0.2 mm / 1 oz copper at 75 C; only the relative
    # resistances affect unit branch currents. Physical barrel spans between
    # actual trace landings are used, not the floating outer barrel tails.
    rho = 1.724e-8 * (1 + .00393 * 55)
    resistance = [rho * length / 1000 / (
        .0002 * 35e-6 if a[2] == b[2] else np.pi * 25e-6 * (300e-6 + 25e-6))
        for a, b, length in es]
    currents, equivalent = unit_currents(network, resistance)
    receipt['resistance_hot_ohm'] = equivalent
    receipt['driver_xyz_mm'] = [v/1000 for v in driver]
    planar = {}
    for (a, b, _), current in zip(es, currents):
        if a[2] == b[2] and max(a[1], b[1]) <= 8000:
            depth = round(-a[2] / 1600)
            xy = tuple(sorted((a[:2], b[:2])))
            assert (depth, xy) not in planar
            planar[depth, xy] = float(current if a <= b else -current)
    return receipt, planar


def inspect(path, layers):
    edges, counts = raw_edges(path, layers)
    points = defaultdict(set)
    for net, a, b in edges:
        if abs(a[2]-b[2]) < 1e-5:
            for p in (a, b):
                points[key(p)].add(net)
    shared = [p for p, nets in points.items() if len(nets) == 3]
    assert len(shared) == 1
    star = shared[0]
    assert star[2] == -1600 * (layers-1)
    diagnostic, assignments = [], []
    for net, a, b in edges:
        if abs(a[2]-b[2]) > 1e-5:
            hits = [(p, nets) for p, nets in points.items()
                    if p[:2] == key(a)[:2]
                    and min(a[2], b[2])*1000-.01 <= p[2] <= max(a[2], b[2])*1000+.01]
            if net == '0':
                nets = set.union(*(nets for _, nets in hits))
                assert len(nets) == 1
                net = next(iter(nets))
                assignments.append(dict(net=net, xy_mm=list(a[:2]),
                                        source_z_span_mm=[a[2], b[2]]))
            lands = sorted(p for p, nets in hits if net in nets)
            assert len(lands) == 2, 'Unexpected via landing topology'
            # Actual endpoints can differ by sub-micron CAD roundoff; use
            # snapped XY consistently, while retaining their physical Z.
            a, b = (tuple(v/1000 for v in p) for p in lands)
        diagnostic.append((net, a, b))
    assert len(assignments) == 3 * (layers//2-1)
    receipt = dict(source_sha256=sha(path), entity_counts=counts,
                   supplied_file_modified=False,
                   unassigned_series_barrels=len(assignments),
                   diagnostic_barrel_phase_assignments=assignments,
                   shared_star_xyz_mm=[v/1000 for v in star], phases={})
    currents = {}
    for net in 'ABC':
        receipt['phases'][net], currents[net] = graph(diagnostic, net, star)
        original, _ = graph(edges, net, star)
        receipt['phases'][net]['original_connected_before_barrel_assignment'] = original['connected']
    return receipt, currents


def compare_pairs(currents, reference, pairs):
    result = {}
    for phase in 'ABC':
        result[phase] = []
        for pair in range(pairs):
            common = [(value, reference[phase][depth % 2, xy])
                      for (depth, xy), value in currents[phase].items()
                      if depth//2 == pair and (depth % 2, xy) in reference[phase]]
            if not common:
                result[phase].append(dict(connected=False))
                continue
            a, b = np.array(common).T
            carrying = (abs(a) > 1e-6) & (abs(b) > 1e-6)
            result[phase].append(dict(connected=True, shared_planar_edges=len(common),
                directed_current_cosine=float(a @ b / np.linalg.norm(a) / np.linalg.norm(b)),
                same_direction_fraction=float(np.mean(a[carrying] * b[carrying] > 0))))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = dict(scope=__doc__, current_width_mm=.2, copper_oz=1, temperature_c=75,
                  endpoint_snap_mm=.001, cases={})
    reference = None
    for layers in (2, 4, 6):
        case, currents = inspect(args.directory/f'star-wye_{layers}-layer.dxf', layers)
        if reference is None:
            reference = currents
        case['pairs_top_to_bottom_compared_with_two_layer'] = compare_pairs(currents, reference, layers//2)
        report['cases'][str(layers)] = case
    # Controls on actual copper, not a force scalar fitted to the expected result.
    for net in 'ABC':
        assert report['cases']['2']['phases'][net]['connected']
        assert report['cases']['4']['phases'][net]['connected']
    for net in 'BC':
        pairs = report['cases']['4']['pairs_top_to_bottom_compared_with_two_layer'][net]
        assert pairs[0]['directed_current_cosine'] > .99 and pairs[1]['directed_current_cosine'] < -.99
    assert not report['cases']['6']['phases']['B']['connected']
    assert report['cases']['6']['pairs_top_to_bottom_compared_with_two_layer']['C'][1]['directed_current_cosine'] < -.99
    for layers, case in report['cases'].items():
        assert sha(args.directory/f'star-wye_{layers}-layer.dxf') == case['source_sha256']
    report['status'] = 'verified-actual-source-defects-and-half-cycle-pair-reversal-no-source-repair'
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
