"""Audit actual two-layer DXFs against native imports and signed force receipts.

Uses the supplied centerlines, not regenerated windings. Reconstructs the
endpoint graph directly from DXF, checks every imported trace/via, and compares
independently solved branch currents and layer forces. Copper width is an
explicit assumption, not information in a LINE entity.
"""
import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from audit_braid_layer_force import audit as layer_audit
from audit_move_commutation import fundamental_audit
from winding_oracle import edge_points, resistances, unit_currents
from source_snapshot import capture


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_edges(path, expected_layers=2):
    lines = path.read_text().splitlines()
    pairs = [(int(c), v.strip()) for c, v in zip(lines[::2], lines[1::2])]
    begin = next(i + 2 for i in range(len(pairs)-1)
                 if pairs[i] == (0, 'SECTION') and pairs[i+1] == (2, 'ENTITIES'))
    end = next(i for i in range(begin, len(pairs)) if pairs[i] == (0, 'ENDSEC'))
    entities = []
    for code, value in pairs[begin:end]:
        if code == 0:
            entities.append((value, {}))
        else:
            entities[-1][1][code] = value
    result = []
    counts = Counter(kind for kind, _ in entities)
    i = 0
    while i < len(entities):
        kind, fields = entities[i]
        net = fields.get(8, '').split('_')[-1]
        point = lambda codes, f=fields: tuple(float(f.get(c, '0')) for c in codes)
        if kind == 'LINE':
            result.append((net, point([10,20,30]), point([11,21,31])))
        elif kind == 'POLYLINE':
            flags = int(fields.get(70, '0'))
            assert flags in (0, 8), 'This audit supports only open straight polylines'
            points = []
            i += 1
            while entities[i][0] == 'VERTEX':
                v = entities[i][1]
                assert float(v.get(42, '0')) == 0
                points.append((float(v[10]), float(v[20]),
                               float(v.get(30, '0') if flags & 8 else fields.get(30, '0'))))
                i += 1
            assert entities[i][0] == 'SEQEND'
            result.extend((net, a, b) for a,b in zip(points, points[1:]))
        else:
            raise ValueError('Unsupported entity in actual supplied DXF: '+kind)
        i += 1
    levels = {round(p[2], 5) for _,a,b in result for p in (a,b)}
    assert levels == {round(-1.6 * i, 5) for i in range(expected_layers)}
    return result, dict(counts)


def key(point):
    return tuple(int(np.rint(v * 1000)) for v in point)


def edge_key(net, a, b):
    return net, *sorted((tuple(round(v, 6) for v in a), tuple(round(v, 6) for v in b)))


def planar_contacts(edges):
    """Check centerline crossings that an endpoint-only graph could miss."""
    planar = [(net,np.array(a,dtype=float),np.array(b,dtype=float)) for net,a,b in edges if a[2]==b[2]]
    missed = []
    cross_net = []
    cross = lambda a,b: float(a[0]*b[1]-a[1]*b[0])
    for i,(net,a,b) in enumerate(planar):
        for other,c,d in planar[i+1:]:
            if a[2]!=c[2]:
                continue
            if np.any(np.maximum(np.minimum(a[:2],b[:2]),np.minimum(c[:2],d[:2])) > np.minimum(np.maximum(a[:2],b[:2]),np.maximum(c[:2],d[:2]))+1e-5):
                continue
            r,s=b[:2]-a[:2],d[:2]-c[:2]
            determinant=cross(r,s)
            if abs(determinant)<1e-12:
                # Actual DXFs have collinear joins, not overlapping traces.
                if abs(cross(c[:2]-a[:2],r))>1e-5*np.linalg.norm(r):
                    continue
                axis=int(np.argmax(abs(r)))
                overlap=min(max(a[axis],b[axis]),max(c[axis],d[axis]))-max(min(a[axis],b[axis]),min(c[axis],d[axis]))
                assert overlap<1e-5, 'Overlapping actual copper requires an explicit union model'
                continue
            t=cross(c[:2]-a[:2],s)/determinant
            u=cross(c[:2]-a[:2],r)/determinant
            tolerance=1e-5/max(np.linalg.norm(r),np.linalg.norm(s))
            if not (-tolerance<=t<=1+tolerance and -tolerance<=u<=1+tolerance):
                continue
            p=a.copy();p[:2]+=t*r
            at_ends=min(np.linalg.norm(p-a),np.linalg.norm(p-b))<1e-5 and min(np.linalg.norm(p-c),np.linalg.norm(p-d))<1e-5
            contact=dict(nets=[net,other],xyz_mm=p.tolist(),both_are_endpoints=bool(at_ends))
            if net!=other:
                cross_net.append(contact)
            if not at_ends:
                missed.append(contact)
    assert not missed, 'Endpoint network misses real planar junctions: '+str(missed[:5])
    return dict(unmodeled_planar_junctions=missed,cross_phase_centerline_contacts=cross_net)


def topology(path, project, fixture):
    raw, counts = raw_edges(path)
    cad = project['versions'][0]['state']['cad_geometry']
    zs = cad['layer_z_mm']
    imported = []
    for s in cad['routing']['segments']:
        point = lambda p: (p['x'],p['y'],zs[s['layer']])
        imported.append((s['net'],point(s['start']),point(s['end'])))
    for v in cad['routing']['vias']:
        p = v['position']
        imported.append((v['net'], (p['x'],p['y'],zs[v['from_layer']]),
                         (p['x'],p['y'],zs[v['to_layer']])))
    assert Counter(edge_key(*e) for e in raw) == Counter(edge_key(*e) for e in imported), 'Import changed actual DXF copper'
    by_net = {}
    raw_nodes = defaultdict(set)
    for net in 'ABC':
        edges = [(key(a),key(b)) for n,a,b in raw if n == net]
        adjacency = defaultdict(list)
        for a,b in edges:
            adjacency[a].append(b)
            adjacency[b].append(a)
            raw_nodes[a].add(net)
            raw_nodes[b].add(net)
        seen = set()
        pending = [next(iter(adjacency))]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(adjacency[node])
        assert len(seen) == len(adjacency), 'Disconnected raw DXF copper'
        native = next(n for n in fixture['networks'] if n['net'] == net)
        assert native['node_count'] == len(adjacency)
        assert len(native['edges']) == len(edges)
        # Bind every native graph node to physical XYZ independently, checking
        # endpoint merges and all via landings, not just graph-size agreement.
        native_nodes = {}
        for edge in native['edges']:
            points = edge_points(edge, fixture['sim'], fixture['geometry_hints']) * 1000
            for index,p in [(edge['a'],points[0]),(edge['b'],points[-1])]:
                k = key(p)
                assert index not in native_nodes or native_nodes[index] == k
                native_nodes[index] = k
        assert len(set(native_nodes.values())) == len(adjacency)
        assert set(native_nodes.values()) == set(adjacency)
        assert Counter(tuple(sorted((native_nodes[e['a']],native_nodes[e['b']]))) for e in native['edges']) == Counter(tuple(sorted(e)) for e in edges)
        degree_one = [p for p,neighbors in adjacency.items() if len(neighbors) == 1]
        by_net[net] = dict(nodes=len(adjacency),edges=len(edges),connected=True,
                          cycles=len(edges)-len(adjacency)+1,
                          degree_histogram=dict(Counter(map(len,adjacency.values()))),
                          dangling_xyz_mm=[[v/1000 for v in p] for p in sorted(degree_one)],
                          driver_xyz_mm=[[v/1000 for v in native_nodes[i]] for i in native['terminal']],
                          neutral_xyz_mm=[[v/1000 for v in native_nodes[i]] for i in native['star']])
    shared = [p for p,nets in raw_nodes.items() if len(nets)>1]
    assert len(shared) == 1 and len(raw_nodes[shared[0]]) == 3
    return dict(entity_counts=counts,planar_trace_count=len(cad['routing']['segments']),
                via_count=len(cad['routing']['vias']),physical_layer_z_mm=zs,
                actual_dxf_import_and_graph_match=True,
                shared_neutral_xyz_mm=[v/1000 for v in shared[0]],phases=by_net,
                planar_contacts=planar_contacts(raw))


def balanced_force(positions, force, period, reference):
    theta = 2*np.pi*np.asarray(positions)/period
    currents = np.sin(theta[:,None] + reference - np.arange(3)*2*np.pi/3)
    assert np.max(abs(currents.sum(axis=1))) < 1e-12
    total = np.sum(np.asarray(force)*currents,axis=1)
    return dict(reference_deg=float(np.degrees(reference)),phase_peak_current_a=1,
                min_n=float(total.min()),mean_n=float(total.mean()),max_n=float(total.max()),
                peak_to_peak_over_mean=float(np.ptp(total)/abs(total.mean())),
                positions_m=list(positions),force_n=total.tolist())


def audit_case(path, project_path, work):
    project = json.loads(project_path.read_text())
    result = dict(dxf_sha256=sha(path),project_sha256=sha(project_path),levels={})
    for mesh in [20,40]:
        fixture_path = work/f'mesh-{mesh}'/'fixture.json'
        fixture = json.loads(fixture_path.read_text())
        if mesh == 40:
            result['topology'] = topology(path,project,fixture)
        layers = layer_audit(fixture_path,fixture_path)
        signed = fixture['signed_force_audit']
        x = np.array([p['position_m'] for p in signed['force_map']])
        f = np.array([p['force_n_per_a'] for p in signed['force_map']])
        low,high = signed['full_overlap_bounds_m']
        period = signed['electrical_period_m']
        # Two complete interior electrical cycles selected by geometry only.
        low += period
        high = low + np.floor((high-period-low)/period)*period
        axes = fundamental_audit(x,f,period,low,high)
        result['levels'][str(mesh)] = dict(fixture_sha256=sha(fixture_path),layers=layers,axes=axes)
    result['force_map'] = signed
    return result


def compare_currents(compact,spread):
    result = {}
    for net in 'ABC':
        maps = []
        for data in (compact,spread):
            network = next(n for n in data['networks'] if n['net']==net)
            shares,_ = unit_currents(network,resistances(network,data['sim'],data['drive'],data['geometry_hints']))
            edges = {}
            for edge,current in zip(network['edges'],shares):
                p = edge_points(edge,data['sim'],data['geometry_hints'])*1000
                a,b = (tuple(round(v,6) for v in row) for row in (p[0],p[-1]))
                k = tuple(sorted((a,b)))
                assert k not in edges
                edges[k] = float(current if a<=b else -current)
            maps.append(edges)
        common = sorted(set(maps[0])&set(maps[1]))
        a,b = (np.array([m[k] for k in common]) for m in maps)
        carries = abs(a)>1e-5
        result[net] = dict(identical_geometric_edges=len(common),
                           common_current_cosine=float(np.dot(a,b)/np.linalg.norm(a)/np.linalg.norm(b)),
                           same_direction_fraction=float(np.mean(a[carries]*b[carries]>0)),
                           max_same_sign_error_a_per_a=float(np.max(abs(a-b))),
                           max_reversed_sign_error_a_per_a=float(np.max(abs(a+b))))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    parser.add_argument('--compact',type=Path,default=Path('star-wye_2-layer.dxf'))
    parser.add_argument('--spread',type=Path,default=Path('star-wye_2-layer-spread.dxf'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    sources=capture(args.work,[Path(__file__),Path(__file__).parent/'relabel_dxf_phases.py',
        Path(__file__).parent/'audit_braid_layer_force.py',Path(__file__).parent/'audit_move_commutation.py',
        root/'crates/pcbmotorgen-export/src/cad_dxf.rs',root/'app/desktop/src-tauri/src/commands/dxf_audit_tests.rs',
        Path(__file__).parent/'winding_oracle.py',Path(__file__).parent/'prescribed_pm_oracle.py'])
    report=dict(scope=__doc__,source_snapshots=sources,cases={})
    for case,path in [('compact',args.compact),('spread',args.spread)]:
        report['cases'][case]=audit_case(path,args.work/(case+'.pmmotor'),args.work/case)
    compact,spread = (json.loads((args.work/case/'mesh-40'/'fixture.json').read_text()) for case in ['compact','spread'])
    assert compact['sim']==spread['sim'] and compact['drive']==spread['drive']
    sim=compact['sim']
    report['assumptions']=dict(magnet_count=sim['magnet_count'],magnet_dimensions_m=sim['magnet_dims_m'],
        adjacent_NS_pole_pitch_m=sim['magnet_pitch_m'],remanence_t=sim['magnet_remanence_t'],
        air_gap_m=sim['air_gap_m'],active_copper_width_m=sim['board_width_m'],
        copper_layer_z_m=compact['geometry_hints']['layer_z_m'],
        uniform_assumed_trace_width_m=sim['min_trace_m'],drive_settings=compact['drive'],
        force_scope='Prescribed permanent-magnet free-space force at imposed current; no soft magnetic materials, driver dynamics, power or hardware qualification')
    report['shared_geometry_currents']=compare_currents(compact,spread)
    report['uniform_trace_width_sensitivity']={}
    for width in [0.127,0.2,0.35]:
        variants=[copy.deepcopy(d) for d in (compact,spread)]
        errors={}
        for case,data in zip(['compact','spread'],variants):
            data['sim']['min_trace_m']=width/1000
            errors[case]={}
            for net in data['networks']:
                shares,_=unit_currents(net,resistances(net,data['sim'],data['drive'],data['geometry_hints']))
                error=float(np.max(abs(shares-net['rust_current_share'])))
                assert error<1e-8
                errors[case][net['net']]=error
        report['uniform_trace_width_sensitivity'][str(width)]=dict(max_current_change_a_per_a=errors,
            compact_spread_current_comparison=compare_currents(*variants))
    # Identical balanced ABC drive with one common reference, derived only
    # from spread. Also show each winding's best COMMON reference separately.
    reference=report['cases']['spread']['levels']['40']['axes']['positive_sequence_reference_rad']
    for case,c in report['cases'].items():
        m=c['force_map'];points=m['force_map'];period=m['electrical_period_m']
        x=[p['position_m'] for p in points];f=[p['force_n_per_a'] for p in points]
        c['same_balanced_command_full_overlap']=balanced_force(x,f,period,reference)
        axes=c['levels']['40']['axes'];lo,hi=axes['interval_m']
        selected=[i for i,p in enumerate(x) if lo<=p<=hi]
        c['same_balanced_command_interior']=balanced_force([x[i] for i in selected],[f[i] for i in selected],period,reference)
        own=axes['positive_sequence_reference_rad']
        c['best_common_reference_balanced_interior']=balanced_force([x[i] for i in selected],[f[i] for i in selected],period,own)
    # Diagnostic only, NOT another routed design: reverse compact C's physical
    # terminal sense to isolate polarity from spacing. This cannot be done by
    # negating only one inverter current without violating neutral KCL.
    c=report['cases']['compact'];m=c['force_map'];points=m['force_map']
    x=np.array([p['position_m'] for p in points]);f=np.array([p['force_n_per_a'] for p in points]);f[:,2]*=-1
    lo,hi=c['levels']['40']['axes']['interval_m'];selected=(x>=lo)&(x<=hi)
    report['hypothetical_compact_C_terminal_reversal']=dict(
        scope='Force-sign diagnostic only; requires physically reconnecting the winding ends, not software negation of one phase current. No replacement routing has been built or validated.',
        axes=fundamental_audit(x,f,m['electrical_period_m'],lo,hi),
        same_balanced_command_interior=balanced_force(x[selected].tolist(),f[selected],m['electrical_period_m'],reference))
    for path,entry in sources.items():
        assert sha(Path(path))==entry['sha256'], 'Audit source changed during comparison'
    for case,path in [('compact',args.compact),('spread',args.spread)]:
        assert sha(path)==report['cases'][case]['dxf_sha256']
    report['status']='passed-actual-DXF-topology-current-and-signed-force-comparison'
    with (args.output or args.work/'comparison.json').open('x') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
        stream.write('\n')
    for case,c in report['cases'].items():
        print(case,json.dumps(c['levels']['40']['axes'],indent=2))
        print('layer retention', {p:v['retained_amplitude_fraction'] for p,v in c['levels']['40']['layers']['phases'].items()})
        print('same balanced drive', {k:v for k,v in c['same_balanced_command_interior'].items() if k not in ('positions_m','force_n')})
    print('common-edge current comparison',json.dumps(report['shared_geometry_currents'],indent=2))
