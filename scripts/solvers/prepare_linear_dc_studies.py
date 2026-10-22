#!/usr/bin/env python3
"""Bind actual host exports to explicit new linear study/model/return inputs.

No CAD edits, copper substitution, source solve or magnetic acceptance.
"""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np

from closed_winding import build as closed_graph
from compare_reduced_fields import completed_receipt
from dc_request_contract import geometry_descriptor
from finite_copper_geometry import dimensions
from prepare_imported_dc_source import via_records
from project_static import project
from post_project_force import sha
from source_snapshot import capture
from winding_coordinates import translation


def host_exports(text):
    result=[]
    prefix='test commands::dc_jobs::tests::export_saved_dc_geometry_for_independent_qualification ... '
    for line in text.splitlines():
        if line.startswith(prefix):line=line[len(prefix):]
        if not line.startswith('{"'):continue
        value=json.loads(line)
        if {'source_project','source_sha256','version_index','snapshot','snapshot_sha256','imported','qualification_only'}<=value.keys():result.append(value)
    return result


def model_inputs(snapshot,saved_project,version,waypoints,positive,negative):
    geometry_descriptor(snapshot)
    document=json.loads(Path(saved_project).read_text());state=document['versions'][version]['state'];sim=snapshot['sim']
    if state.get('cad_geometry') is not None or state['config']['topology']!='linear':raise ValueError('Actual generated linear source required')
    pose=state['mover_position_mm']*1e-3;length=sim['active_area_length_m'];width=sim['board_width_m']
    if not 0<=pose<=state['config']['desired_travel_mm']*1e-3:raise ValueError('Saved mover pose outside declared travel')
    centre=pose+(sim['magnet_count']-1)*sim['magnet_pitch_m']/2-length/2
    model=project(saved_project,version,[length*1e3,width*1e3],[centre*1e3,0.])
    shift=translation(sim,model,pose)
    if not np.allclose(shift,[-length/2,-width/2,sim['pcb_thickness_m']],rtol=0.,atol=1e-14):raise ValueError('Coordinate mapping moved physical geometry')
    spec=dimensions(snapshot);layers={value['layer']:value for value in spec['layers']}
    lows=[layers[segment['layer']]['centre_z_m']-layers[segment['layer']]['thickness_m']/2 for segment in snapshot['routing']['segments']]
    lows.extend(span['low'] for via in via_records(snapshot).values() for span in via['spans'])
    if not lows:raise ValueError('No actual finite copper')
    low=min(lows)+shift[2];top=max(region['origin_m'][2]+region['size_m'][2] for region in model['stack'])
    if low<=top:raise ValueError('Nominal copper/stack not vertically disjoint;no physical correction permitted')
    _,_,closure=closed_graph(snapshot,positive,negative,shift,waypoints)
    closure['scope']='Explicit declared finite-return screening scenario;graph closure/current checks only,not CAD/source/force qualification or cable recovery.'
    return dict(model=model,translation_m=shift.tolist(),closure=closure,
        preflight=dict(minimum_finite_copper_z_m=low,maximum_stack_z_m=top,vertical_separation_m=low-top,
            method='Conservative exact finite trace/via Z intervals prove vertical separation. Actual BRep intersection/tagging still required before magnetic coupling.'),
        return_width_m=sim['min_trace_m'],return_thickness_m=spec['layers'][0]['thickness_m'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive-root',type=Path,required=True)
    parser.add_argument('--declaration',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    if args.work.exists():parser.error('Preserve earlier actual design studies')
    root=args.archive_root.resolve();declaration=json.loads(args.declaration.read_text())
    if declaration['schema']!='actual-linear-dc-study-inputs-v1':raise ValueError('Explicit actual study inputs required')
    origin=(root/declaration['design_archive']).resolve()
    if not origin.is_relative_to(root):raise ValueError('Declared design archive must remain inside evidence root')
    prepared=json.loads((origin/'summary.json').read_text());by_name={value['case']:value for value in prepared['cases']}
    records=[];inputs={str(args.declaration.resolve()):sha(args.declaration),str(origin/'summary.json'):sha(origin/'summary.json')}
    for case in declaration['cases']:
        saved=by_name[case['id']];source=Path(saved['saved_project']);snapshot_path=origin/(case['id']+'-snapshot.json')
        log=root/(case['id']+'-host-export-v2-20261022.log');receipt=Path(str(log)+'.command.json');completed_receipt({'command_receipt':str(receipt)})
        exports=host_exports(log.read_text())
        if len(exports)!=1 or exports[0]['imported'] or exports[0]['qualification_only']:raise ValueError('Actual production generated host export required')
        metadata=exports[0]
        if metadata['version_index']!=saved['version_index'] or Path(metadata['snapshot']).resolve()!=snapshot_path.resolve() or Path(metadata['source_project']).resolve()!=source.resolve():
            raise ValueError('Actual export path/version identity changed')
        if sha(source)!=case['source_project_sha256'] or sha(snapshot_path)!=case['snapshot_sha256'] or metadata['source_sha256']!=sha(source) or metadata['snapshot_sha256']!=sha(snapshot_path):
            raise ValueError('Saved project/host export/snapshot identity changed')
        snapshot=json.loads(snapshot_path.read_text());study=model_inputs(snapshot,source,saved['version_index'],case['external_return_waypoints_m'],case['positive_phase'],case['negative_phase'])
        records.append((case,snapshot_path,study))
        inputs.update({str(path):sha(path) for path in [source,snapshot_path,log,receipt]})
    args.work.mkdir(parents=True);outputs=[]
    for case,snapshot_path,study in records:
        work=args.work/case['id'];work.mkdir();shutil.copy2(snapshot_path,work/'fixture.json')
        value=dict(status='prepared-actual-linear-study-no-source-or-force-acceptance',scope=__doc__,case=case['id'],
            input_hashes=inputs,fixture_sha256=sha(work/'fixture.json'),**study,
            source_snapshots=capture(work,[Path(__file__),Path(__file__).with_name('project_static.py'),Path(__file__).with_name('winding_coordinates.py'),Path(__file__).with_name('closed_winding.py')]))
        (work/'summary.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');outputs.append(dict(case=case['id'],work=str(work.resolve()),preflight=study['preflight']))
    for path,digest in inputs.items():
        if sha(Path(path))!=digest:raise ValueError('Actual study inputs changed during preparation')
    (args.work/'summary.json').write_text(json.dumps(dict(status='prepared-actual-linear-study-inputs-only',input_hashes=inputs,cases=outputs),indent=2)+'\n')
    print(json.dumps(outputs),flush=True)


if __name__=='__main__':main()
