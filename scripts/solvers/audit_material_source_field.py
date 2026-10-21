#!/usr/bin/env python3
"""Independently reconstruct exterior static field from solved magnetization.

Preserves and reports raw A-curl interpolation rather than correcting/subtracting
a failed force floor. Reconstructed fields must pass volume integration and
scalar-reference gates separately. One job is not mesh/domain qualification.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_project_bare_map import observations
from audit_static_material_controls import load,compare
from material_source_field import material_moments,dipole_field,exterior_points
from ngsolve_reduced import total_field as scalar_field
from post_project_force import sha
from reduced_potential import source_field
from solver_threads import add_thread_option,positive_threads,threaded_main,runtime_metadata
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True);parser.add_argument('--scalar',type=Path,required=True)
    parser.add_argument('--degrees',type=int,nargs=2,default=[6,8]);parser.add_argument('--green-workers',type=positive_threads,default=2)
    parser.add_argument('--output',type=Path,required=True);add_thread_option(parser);args=parser.parse_args();archive=args.output.with_suffix('.npz')
    if args.output.exists() or archive.exists():parser.error('Preserve previous reconstructed-field evidence')
    if not 2<=args.degrees[0]<args.degrees[1]:parser.error('Two increasing material volume rules required')
    report,raw=load(args.work);reference,evaluate=scalar_field(args.scalar)
    if report['model']!=reference['model']:raise ValueError('Different physical material/source cases')
    model=report['model'];maps=observations(model,64,24,both_sides=True);incident=source_field(model)
    for points in maps.values():exterior_points(model,points)
    output={'status':'running','scope':__doc__,'levels':{},'checks':{},'failures':[],
        'execution':dict(runtime_metadata(),green_workers=args.green_workers),
        'input_hashes':{str(p):sha(p) for p in [args.work/'summary.json',args.scalar/'summary.json']},
        'source_snapshots':capture(args.output.parent,[Path(__file__),Path(__file__).with_name('material_source_field.py'),Path(__file__).with_name('vector_material.py'),Path(__file__).with_name('volume_field_quadrature.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save();values={};baseline={};particular={};raw_fields={}
    try:
        for label,points in maps.items():baseline[label]=evaluate(points);particular[label]=incident(points);raw_fields[label]=raw(points)
        for degree in args.degrees:
            _,positions,moments=material_moments(args.work,degree);level={};values[degree]={}
            for label,points in maps.items():
                total=particular[label]+dipole_field(points,positions,moments,args.green_workers);values[degree][label]=total
                level[label]=compare(baseline[label],total,particular[label],.05)
            output['levels'][str(degree)]={'source_points':len(positions),'scalar_comparison':level};save()
        for label in maps:
            reference_check=output['levels'][str(args.degrees[-1])]['scalar_comparison'][label]
            refinement=compare(values[args.degrees[-1]][label],values[args.degrees[0]][label],particular[label],.02)
            output['checks'][label]={'scalar_reference':reference_check,'volume_refinement':refinement,
                'raw_a_curl_reference':compare(baseline[label],raw_fields[label],particular[label],.05)}
            if not reference_check['passed'] or not refinement['passed']:output['failures'].append(label)
        with archive.open('xb') as stream:
            np.savez_compressed(stream,**{f'{name}_{i}':data for i,label in enumerate(maps) for name,data in
                [('points',maps[label]),('source_b',particular[label]),('scalar_b',baseline[label]),('raw_a_curl_b',raw_fields[label]),
                 ('coarse_reconstructed_b',values[args.degrees[0]][label]),('fine_reconstructed_b',values[args.degrees[-1]][label])]})
        output['probe_archive_sha256']=sha(archive)
        for p,digest in output['input_hashes'].items():
            if sha(Path(p))!=digest:raise ValueError('Material field input changed')
        for p,entry in output['source_snapshots'].items():
            if sha(Path(p))!=entry['sha256']:raise ValueError('Reconstruction implementation changed')
        output['status']='failed' if output['failures'] else 'passed-exterior-magnetization-field-reference-and-volume-only';save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':threaded_main(main)
