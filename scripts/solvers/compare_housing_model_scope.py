#!/usr/bin/env python3
"""Matched-input comparison of finite housing with the app's planar model.

Finite array/footprint and source startup differ from an infinite steady
travelling fundamental even when dimensions/material/separation match.
Discrepancies are diagnostic, NOT a numerical acceptance gate or fitted
correction. Full-stroke mean force/energy is never relabeled steady drag.
Only equal alternating axial PMs and a housing-only mu=1 Al case map here.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess

import numpy as np

from audit_housing_motion_controls import load
from check_housing_motion_reference import HOUSING, case_base
from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def mapped_case(record):
    model=record['model'];magnets=model['magnets'];request=record['request'];housing=record['housing']
    if request['slot']!=0:raise ValueError('A slot cannot be silently represented by a planar uncut layer')
    material=housing['material']
    if material not in ['aluminum6061','aluminum5052'] or housing['mu_r']!=1:
        raise ValueError('Need an actual supported mu=1 aluminum source; no stainless permeability remap')
    if not math.isclose(request['sigma'],HOUSING[material][1],rel_tol=1e-12):raise ValueError('Conductivity differs from app material; do not fit/remap')
    magnets=sorted(magnets,key=lambda m:m['origin_m'][0]);dims=np.asarray(magnets[0]['size_m']);origins=np.array([m['origin_m'] for m in magnets]);polar=np.array([m['polarization_t'] for m in magnets])
    if not 2<=len(magnets)<=12:raise ValueError('Outside supported magnet-count envelope')
    pitch=float(origins[1,0]-origins[0,0]);br=abs(polar[0,2])
    if pitch<=0 or br<=0 or np.any(dims<=0):raise ValueError('Invalid PM physical dimensions')
    if any(not np.allclose(m['size_m'],dims,rtol=0,atol=1e-14) for m in magnets):raise ValueError('Unequal PM dimensions cannot be mapped')
    if not np.allclose(np.diff(origins[:,0]),pitch,rtol=0,atol=1e-14) or not np.allclose(origins[:,1:],origins[0,1:],rtol=0,atol=1e-14):raise ValueError('Nonuniform/tilted source cannot be mapped')
    expected=np.zeros_like(polar);expected[:,2]=polar[0,2]*(-1.)**np.arange(len(magnets))
    if not np.allclose(polar,expected,rtol=0,atol=1e-14):raise ValueError('Non-axial/nonalternating PMs cannot be mapped')
    centre=origins[:,:2].mean(axis=0)+dims[:2]/2
    housing_centre=np.asarray(housing['origin_m'][:2])+np.asarray(housing['size_m'][:2])/2
    if not np.allclose(centre,[0.,0.],rtol=0,atol=1e-14) or not np.allclose(housing_centre,[0.,0.],rtol=0,atol=1e-14):
        raise ValueError('Offset array/housing requires an explicitly mapped pose, not a centred substitution')
    pcb=model['pcb_thickness_m'];air=float(origins[0,2]-pcb)
    top=float(housing['origin_m'][2]+housing['size_m'][2]);gap=-top
    if air<0 or not 0<=gap<=.01 or not 0<housing['size_m'][2]<=.005:raise ValueError('Physical gaps/wall outside app envelope')
    case=case_base();sim=case['sim']
    sim.update(magnet_dims_m=dims.tolist(),magnet_count=len(magnets),magnet_pitch_m=pitch,magnet_remanence_t=br,
        pcb_thickness_m=pcb,air_gap_m=air,active_area_length_m=model['footprint_m'][0],board_width_m=model['footprint_m'][1])
    sim['backplane']={'layers':[],'housing':{'material':material,'thickness_m':housing['size_m'][2],'gap_m':gap}}
    case.update(speed_m_s=request['speed'],duration_s=record['profile']['duration_s'])
    actual_separation=float(origins[0,2]-top);app_separation=air+pcb+gap
    if not math.isclose(actual_separation,app_separation,rel_tol=1e-12,abs_tol=1e-14):raise ValueError('Coordinate conversion changed PM-to-housing separation')
    return case,{'coordinate_conversion':'Offline PCB bottom0 -> app PCB top0; translate all physical z by minus PCB thickness',
        'actual_pm_to_housing_surface_m':actual_separation,'app_pm_to_housing_surface_m':app_separation,
        'housing_gap_below_pcb_m':gap,'excluded_offline_regions':record['excluded_materials'],
        'note':'Ferrite is EXCLUDED from both models. Its former thickness remains part of the air gap; housing is not moved.',
        'finite_housing_size_m':housing['size_m'],'finite_housing_origin_m':housing['origin_m'],
        'finite_pm_origins_m':origins.tolist()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finite-work',type=Path,required=True);parser.add_argument('--finite-controls',type=Path,required=True)
    parser.add_argument('--binary',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    if args.work.exists():parser.error('Preserve earlier model comparisons')
    finite=args.finite_work.resolve();binary=args.binary.resolve();record=load(finite);case,mapping=mapped_case(record)
    controls=json.loads(args.finite_controls.read_text());completed_receipt(controls)
    if controls['status'] not in ['passed-full-entry-exit-and-slot-controls-source-only','passed-full-stroke-housing-time-pair-only','passed-full-stroke-housing-mesh-pair-only'] or controls.get('failures'):
        raise ValueError('Finite reference controls failed or unsupported; no qualified reference comparison')
    sources=controls.get('source_summary_sha256',controls.get('input_hashes',{}))
    if sha(finite/'summary.json') not in sources.values():raise ValueError('Controls do not belong to this finite trajectory')
    hashes={'finite_summary':sha(finite/'summary.json'),'binary':sha(binary),'finite_controls':sha(args.finite_controls)}
    args.work.mkdir(parents=True);input_path=args.work/'matched-planar.input.json';input_path.write_text(json.dumps(case,indent=2,allow_nan=False)+'\n')
    process=subprocess.run([str(binary),str(input_path)],capture_output=True,text=True,timeout=60)
    (args.work/'planar.stdout.json').write_text(process.stdout);(args.work/'planar.stderr.log').write_text(process.stderr)
    if process.returncode:raise ValueError('Mapped app calculation unavailable; no fallback accepted')
    planar=json.loads(process.stdout)
    if planar['status']!='experimental':raise ValueError('No accepted app result')
    estimate=planar['estimate'];half=case['sim']['magnet_pitch_m']/4
    rows=[r for r in record['steps'] if abs(r['source_offset_m'])<=half]
    if len(rows)<2:raise ValueError('No centre-region samples; do not compare full-path mean with steady drag')
    power=np.array([r['joule_power_w'] for r in rows]);fx=np.array([r['housing_source_interaction_force_n'][0] for r in rows])
    result={'status':'completed-matched-input-model-discrepancy-diagnostic-only','scope':__doc__,
        'input_hashes':hashes,'mapping':mapping,'planar':planar,'finite_control_scope':controls['status'],
        'centre_region':{'offset_interval_m':[-half,half],'samples':len(rows),'finite_power_range_w':[float(power.min()),float(power.max())],
            'finite_mean_power_w':float(power.mean()),'finite_mean_housing_interaction_fx_n':float(fx.mean()),
            'finite_mean_power_over_planar_steady_power':float(power.mean()/estimate['housing_joule_power_w']),
            'interpretation':'Same physical separation/material/source dimensions, different finite-array/finite-housing/startup model. Not steady-state or isolated edge-error validation.'},
        'whole_finite_profile':{'heat_j':record['joule_energy_j'],'source_work_j':record['source_work_energy_j'],
            'final_reaction_energy_j':record['reaction_energy_end_j'],'scope':'Full entry/exit integral retained separately; no ratio to steady full-duration heat is used as an accuracy gate.'},
        'source_snapshots':capture(args.work,[Path(__file__),*[Path(__file__).with_name(name) for name in ['audit_housing_motion_controls.py','check_housing_motion_reference.py','compare_reduced_fields.py']]])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):result['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    if sha(finite/'summary.json')!=hashes['finite_summary'] or sha(binary)!=hashes['binary'] or sha(args.finite_controls)!=hashes['finite_controls']:raise ValueError('Physical reference, control or app executable changed')
    (args.work/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(result['status'],result['centre_region'],flush=True)


if __name__=='__main__':main()
