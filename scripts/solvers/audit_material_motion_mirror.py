#!/usr/bin/env python3
"""Mirrored constant-speed nonlinear short-stroke control, not a reversal cycle.

Loads two whole completed trajectories with identical physical model/mesh and
opposite prescribed speeds. Checks heat, energy changes, and longitudinal and
vector housing/material forces separately so static attraction cannot hide a
failed drag control. Applies only to explicitly x-symmetric reversible models.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_material_motion_controls import load
from post_project_force import sha
from source_snapshot import capture


def symmetric_model(model):
    for layer in model['stack']:
        if not np.isclose(layer['origin_m'][0]+layer['size_m'][0]/2,0.,rtol=0,atol=1e-14):
            raise ValueError('Material footprint is not x symmetric')
    magnets=sorted(model['magnets'],key=lambda m:m['origin_m'][0]);parities=[]
    for a,b in zip(magnets,reversed(magnets)):
        if not np.allclose(a['size_m'],b['size_m'],rtol=0,atol=1e-14):raise ValueError('Source dimensions not symmetric')
        reflected=np.array(a['origin_m']);reflected[0]=-reflected[0]-a['size_m'][0]
        if not np.allclose(reflected,b['origin_m'],rtol=0,atol=1e-14):raise ValueError('Source origins not symmetric')
        p=np.array(a['polarization_t']);q=np.array(b['polarization_t'])
        if not np.isfinite(p).all() or not np.isfinite(q).all() or np.linalg.norm(p)==0:raise ValueError('Invalid PM polarization')
        # Axial-vector reflection reverses y/z components. A reversible
        # B-energy permits one GLOBAL additional magnetic sign inversion.
        reflected_p=p*np.array([1.,-1.,-1.])
        if np.allclose(q,reflected_p,rtol=0,atol=1e-14):parities.append(1)
        elif np.allclose(q,-reflected_p,rtol=0,atol=1e-14):parities.append(-1)
        else:raise ValueError('PM polarization lacks reflection symmetry')
    if len(set(parities))!=1:raise ValueError('Source requires inconsistent magnetic sign inversions')


def mirror_checks(a,b):
    symmetric_model(a['model'])
    for key in ['model','source_summary_sha256','version','mesh_sha256']:
        if a[key]!=b[key]:raise ValueError('Mirrored control changed physical model, mesh or solver')
    qa,qb=a['request'],b['request'];ignore={'speed','start_x','save_every','max_dofs'}
    if any(qa.get(k)!=qb.get(k) for k in set(qa)|set(qb) if k not in ignore):raise ValueError('Mirrored control changed other numerical/physical inputs')
    if qa['speed']==0 or qb['speed']!=-qa['speed']:raise ValueError('Need exact nonzero opposite velocities')
    pa,pb=a['profile'],b['profile']
    if not all(np.isclose(pa[k],pb[k],rtol=1e-12,atol=1e-15) for k in ['dt_s','duration_s']):raise ValueError('Mirrored time controls differ')
    if any(not np.isclose(pa[k],-pb[k],rtol=1e-12,atol=1e-14) for k in ['start_offset_m','end_offset_m']):raise ValueError('Source stroke is not mirrored')
    if len(a['steps'])!=len(b['steps']):raise ValueError('Mirrored trace lengths differ')
    if not np.allclose([r['source_offset_m'] for r in a['steps']],[-r['source_offset_m'] for r in b['steps']],rtol=1e-12,atol=1e-14):raise ValueError('Source pose histories are not mirrored')
    checks={}
    def check(name,x,y,floor):
        x=np.asarray(x);y=np.asarray(y);error=float(np.linalg.norm(x-y));limit=max(floor,.02*float(np.linalg.norm(y)))
        checks[name]={'absolute_change':error,'limit':limit,'passed':bool(np.isfinite(error) and error<=limit)}
    for field in ['joule_energy_j','mechanical_source_energy_j']:check(field,a[field],b[field],1e-12)
    for field in ['joule_power_w','mechanical_source_work_w']:
        check(field,[r[field] for r in a['steps']],[r[field] for r in b['steps']],1e-10*np.sqrt(len(a['steps'])))
    for field in ['housing_source_force_n','material_source_force_n']:
        first=np.array([r[field] for r in a['steps']]);second=np.array([r[field] for r in b['steps']])*[-1.,1.,1.]
        floor=1e-8*np.sqrt(len(first));check(field,first,second,floor)
        check(field+'_longitudinal',first[:,0],second[:,0],floor)
    ea=np.array([r['reduced_magnetic_energy_end_j'] for r in a['steps']])-a['initial_reduced_energy_j']
    eb=np.array([r['reduced_magnetic_energy_end_j'] for r in b['steps']])-b['initial_reduced_energy_j']
    check('stored_energy_change_history_j',ea,eb,1e-12*np.sqrt(len(ea)))
    check('final_energy_change_j',ea[-1],eb[-1],1e-12)
    return {'checks':checks,'passed':all(c['passed'] for c in checks.values())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['forward','mirrored','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous mirror-control evidence')
    report={'status':'running','scope':__doc__,'source_snapshots':capture(args.output.parent,[Path(__file__),Path(__file__).with_name('audit_material_motion_controls.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    try:
        first=load(args.forward);second=load(args.mirrored);result=mirror_checks(first,second)
        report.update(status='passed-mirrored-nonlinear-short-stroke-only' if result['passed'] else 'failed',result=result,
            input_hashes={str(p.resolve()/'summary.json'):sha(p/'summary.json') for p in [args.forward,args.mirrored]})
        args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        if not result['passed']:raise ValueError('Nonlinear mirrored control failed unchanged2% checks')
    except BaseException as error:
        report.update(status='failed',error=str(error));args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');raise


if __name__=='__main__':main()
