#!/usr/bin/env python3
"""Integrate signed winding Lorentz coefficients in a completed PM-biased field.

Reports force ON COPPER per phase ampere at zero winding excitation, not mover
Kf. A finite magnetic stator can share the incremental force, so negating this
coefficient does not establish mover thrust. No winding-current bias change,
differential inductance, AC, drive waveform or motion is solved. Material
footprint remains the explicitly archived prototype footprint, not housing CAD.
Air-side observation offsets are refined explicitly, never hidden in geometry.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from compare_reduced_fields import completed_receipt,field_case
from post_project_force import sha
from reduced_potential import source_field
from source_snapshot import capture
from winding_coordinates import translate_samples
from winding_oracle import resistances,unit_currents,conductor_samples


def lorentz_coefficient(dl,field):
    dl=np.asarray(dl,dtype=float);field=np.asarray(field,dtype=float)
    if dl.ndim!=2 or dl.shape[1]!=3 or field.shape!=dl.shape or not np.isfinite([dl,field]).all():
        raise ValueError('Invalid current-weighted line elements or magnetic field')
    return np.cross(dl,field).sum(axis=0)


def reference_for(backends,index):
    """Keep same-backend refinement at 2%, even after a 5% backend comparison."""
    previous=next((i for i in range(index) if backends[i]==backends[index]),None)
    return (previous,.02) if previous is not None else (0,.05)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copper-work',type=Path,required=True);parser.add_argument('--field-work',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();copper=args.copper_work.resolve()
    if args.output.exists():parser.error('Preserve previous coupling audits')
    exported=json.loads((copper/'summary.json').read_text());completed_receipt(exported)
    if exported['status']!='passed-original-version-copper-export-only' or exported['failures']:
        raise ValueError('Original-version copper export has not passed')
    audit_path=copper/'free-space-copper-audit/summary.json';audit=json.loads(audit_path.read_text())
    if sha(audit_path)!=exported['copper_audit_sha256']:raise ValueError('Copper audit changed')
    original=json.loads((copper/'original.pmmotor').read_text())
    if sha(copper/'original.pmmotor')!=exported['source_project_sha256']:raise ValueError('Original winding project changed')
    source_state=original['versions'][exported['version_index']]['state']
    mover_position=source_state['mover_position_mm']*1e-3
    fields=[field_case(p.resolve()) for p in args.field_work]
    for report,_,_,_ in fields:
        model=report['model']
        if model['source_sha256']!=exported['source_project_sha256'] or model['version_index']!=exported['version_index']:
            raise ValueError('Bias does not belong to the exported saved version')
        if model!=fields[0][0]['model']:raise ValueError('Coupled fields have different physical models')
    snapshots=capture(args.output.parent,[Path(__file__),*[Path(__file__).with_name(n) for n in
        ['winding_coordinates.py','winding_oracle.py','compare_reduced_fields.py','ngsolve_reduced.py','read_vtu.py']]])
    output={'status':'running','scope':__doc__,'copper_summary_sha256':sha(copper/'summary.json'),
        'field_summary_sha256':[sha(p/'summary.json') for p in args.field_work],
        'saved_mover_position_m':mover_position,'air_side_offsets_m':[1e-7,5e-8],
        'material_footprint_m':fields[0][0]['model']['footprint_m'],
        'levels':{},'checks':{},'failures':[],'source_snapshots':snapshots}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for level,entry in audit['levels'].items():
            fixture_path=copper/f'free-space-copper-audit/mesh-{level}/fixture.json'
            if sha(fixture_path)!=entry['fixture_sha256']:raise ValueError('Conductor fixture changed')
            fixture=json.loads(fixture_path.read_text());sim=fixture['sim'];hints=fixture['geometry_hints']
            result={}
            for network in fixture['networks']:
                resistance=resistances(network,sim,fixture['drive'],hints);shares,equivalent=unit_currents(network,resistance)
                points,dl=conductor_samples(network,shares,sim,hints,int(level))
                mapped,dl=translate_samples(points,dl,sim,fields[0][0]['model'],mover_position)
                if np.min(mapped[:,2]) < -1e-12:raise ValueError('Conductor lies inside the material half-space')
                phase={'resistance_ohm':equivalent,'sample_count':len(mapped),'coefficients':{}}
                for offset in output['air_side_offsets_m']:
                    observations=mapped+np.array([0.,0.,offset])
                    coefficients=[]
                    for report,_,evaluate,backend in fields:
                        if np.max(np.linalg.norm(observations,axis=1))>=.95*report['air_radius_m']:
                            raise ValueError('Conductor samples approach or exceed finite field domain')
                        total=evaluate(observations)
                        incident=source_field(report['model'])(observations)
                        coefficients.append({'backend':backend,'copper_force_n_per_a':lorentz_coefficient(dl,total).tolist(),
                            'prescribed_pm_only_n_per_a':lorentz_coefficient(dl,incident).tolist(),
                            'material_response_n_per_a':lorentz_coefficient(dl,total-incident).tolist()})
                    phase['coefficients'][str(offset)]=coefficients
                result[network['net']]=phase
            output['levels'][level]=result;save();print('copper quadrature',level,'complete',flush=True)
        labels=sorted(output['levels'],key=int)
        if len(labels)<2:raise ValueError('Need at least two copper quadrature levels')
        fine=output['levels'][labels[-1]];prior=output['levels'][labels[-2]]
        def check(name,a,b,tolerance):
            error=float(np.linalg.norm(np.array(a)-b));limit=max(1e-8,tolerance*float(np.linalg.norm(b)))
            output['checks'][name]={'error_n_per_a':error,'limit_n_per_a':limit,'passed':error<=limit}
            if error>limit:output['failures'].append(name)
        offsets=[str(v) for v in output['air_side_offsets_m']]
        for phase,data in fine.items():
            for i in range(len(fields)):
                for quantity in ['copper_force_n_per_a','material_response_n_per_a']:
                    current=data['coefficients'][offsets[-1]][i][quantity]
                    check(f'{phase}/{i}/{quantity}/copper-refinement',prior[phase]['coefficients'][offsets[-1]][i][quantity],current,.02)
                    check(f'{phase}/{i}/{quantity}/air-side-limit',data['coefficients'][offsets[0]][i][quantity],current,.02)
                    if i:
                        reference,tolerance=reference_for([field[3] for field in fields],i)
                        check(f'{phase}/{i}/{quantity}/field-agreement',data['coefficients'][offsets[-1]][reference][quantity],current,tolerance)
        for path,entry in snapshots.items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Coupling implementation changed')
        if [sha(p/'summary.json') for p in args.field_work]!=output['field_summary_sha256']:
            raise ValueError('Bias report changed during coupling')
        if sha(copper/'summary.json')!=output['copper_summary_sha256']:
            raise ValueError('Copper report changed during coupling')
        output['status']='failed' if output['failures'] else 'passed-fixed-bias-copper-lorentz-coefficients-only'
        save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
