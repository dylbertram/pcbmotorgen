"""Compare an unchanged actual DXF variant to an imported reference receipt.

Phase permutation is explicit and changes the controller assignment only.
No winding-current signs or physical terminal directions are reversed.
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np

from audit_compact_spread_dxf import audit_case, balanced_force, compare_currents, sha
from audit_move_commutation import fundamental_audit
from source_snapshot import capture


def map_arrays(fixture):
    signed=fixture['signed_force_audit']
    assert signed['phase_names']==['A','B','C']
    x=np.array([p['position_m'] for p in signed['force_map']])
    force=np.array([p['force_n_per_a'] for p in signed['force_map']])
    return x,force,signed['electrical_period_m']


def opening_positions(project):
    cad=project['versions'][0]['state']['cad_geometry']
    openings={}
    for s in cad['routing']['segments']:
        if cad['layer_z_mm'][s['layer']]!=0:
            continue
        a,b=s['start'],s['end']
        if min(a['y'],b['y'])>=8-1e-5 and max(a['y'],b['y'])>8.1:
            for p in (a,b):
                if abs(p['y']-8)<1e-5:
                    assert s['net'] not in openings
                    openings[s['net']]=p['x']
    assert set(openings)==set('ABC')
    return dict(by_supplied_label_mm=openings,span_mm=max(openings.values())-min(openings.values()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',type=Path,required=True)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--oracle',type=Path,required=True)
    parser.add_argument('--reference-dxf',type=Path,required=True)
    parser.add_argument('--reference-project',type=Path,required=True)
    parser.add_argument('--reference-oracle',type=Path,required=True)
    parser.add_argument('--phase-order',nargs=3,choices=list('ABC'),required=True,
                        help='Variant labels to assign to controller A B C, respectively')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert set(args.phase_order)==set('ABC')
    work=args.output.parent
    sources=capture(work,[Path(__file__),Path(__file__).parent/'audit_compact_spread_dxf.py',
        Path(__file__).parent/'audit_braid_layer_force.py',Path(__file__).parent/'audit_move_commutation.py',
        Path(__file__).parent/'winding_oracle.py',Path(__file__).parent/'prescribed_pm_oracle.py'])
    hashes={str(path.resolve()):sha(path) for path in [args.variant,args.project,args.reference_dxf,args.reference_project]}
    result=dict(scope=__doc__,status='running',source_snapshots=sources,input_sha256=hashes,
                supplied_file_modified=False,controller_ABC_assigned_to_variant_labels=args.phase_order,
                winding_signs_changed=False)
    result['variant']=audit_case(args.variant,args.project,args.oracle)
    variant=json.loads((args.oracle/'mesh-40'/'fixture.json').read_text())
    reference=json.loads((args.reference_oracle/'mesh-40'/'fixture.json').read_text())
    assert variant['sim']==reference['sim'] and variant['drive']==reference['drive']
    assert variant['geometry_hints']==reference['geometry_hints']
    result['sim']=variant['sim'];result['drive']=variant['drive'];result['geometry_hints']=variant['geometry_hints']
    x,force,period=map_arrays(variant)
    rx,rf,rperiod=map_arrays(reference)
    np.testing.assert_array_equal(x,rx);assert period==rperiod
    lo,hi=result['variant']['levels']['40']['axes']['interval_m']
    selected=(x>=lo)&(x<=hi)
    ref_axes=fundamental_audit(rx,rf,rperiod,lo,hi)
    common_ref=ref_axes['positive_sequence_reference_rad']
    order=['ABC'.index(p) for p in args.phase_order]
    mapped_force=force[:,order]
    result['mapped_axes']=fundamental_audit(x,mapped_force,period,lo,hi)
    result['interior_force']={name:balanced_force(x[selected].tolist(),f[selected],period,common_ref)
        for name,f in [('as_supplied_ABC',force),('phase_assignment_matched',mapped_force),('reference',rf)]}
    mapped=copy.deepcopy(variant)
    rename={p:'ABC'[i] for i,p in enumerate(args.phase_order)}
    for network in mapped['networks']:
        network['net']=rename[network['net']]
    result['shared_conductor_currents']=compare_currents(mapped,reference)
    result['all_phase_mesh_refinement']={}
    for name,folder in [('variant',args.oracle),('reference',args.reference_oracle)]:
        coarse=json.loads((folder/'mesh-20'/'fixture.json').read_text())
        fine=json.loads((folder/'mesh-40'/'fixture.json').read_text())
        cx,cf,_=map_arrays(coarse);fx,ff,_=map_arrays(fine)
        np.testing.assert_array_equal(cx,fx)
        change=np.linalg.norm(ff-cf,axis=0);norm=np.linalg.norm(ff,axis=0)
        limit=np.maximum(1e-8,.02*norm);assert np.all(change<=limit)
        result['all_phase_mesh_refinement'][name]=dict(norm_change_n_per_a=change.tolist(),
            relative_norm_change=(change/norm).tolist(),limit_n_per_a=limit.tolist(),passed=True)
    result['openings']={name:opening_positions(json.loads(path.read_text()))
                        for name,path in [('variant',args.project),('reference',args.reference_project)]}
    result['oracle_summary_sha256']={name:sha(folder/'summary.json')
        for name,folder in [('variant',args.oracle),('reference',args.reference_oracle)]}
    for path,digest in hashes.items():assert sha(Path(path))==digest
    for path,entry in sources.items():assert sha(Path(path))==entry['sha256']
    result['status']='passed-actual-DXF-variant-topology-current-force-and-phase-assignment-audit'
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print('As supplied phase axes:',result['variant']['levels']['40']['axes']['phase_sine_offset_deg'])
    print('Mapped phase axes:',result['mapped_axes']['phase_sine_offset_deg'])
    print('Openings:',result['openings'])
    for name,values in result['interior_force'].items():
        print(name,{k:v for k,v in values.items() if k not in ('positions_m','force_n')})
    print('Shared-conductor currents:',result['shared_conductor_currents'])


if __name__=='__main__':
    main()
