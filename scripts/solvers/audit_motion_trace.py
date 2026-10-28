#!/usr/bin/env python3
"""Recompute a completed periodic motion trace from its saved coefficient states.

Checks the actual nonlinear equations, BDF2 derivative, mechanically differentiated
force, Joule heat and source work. This is an internal numerical audit, not an
independent nonlinear FEM or finite-housing current-return validation.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from periodic_motion import moving_source,sampled_diagnostics
from spectral_biased_ac import bias_state
from spectral_transient import Transient
from spectral_plate import MU0
from source_snapshot import capture


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative_difference(a,b):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('Malformed trace comparison')
    return float(np.linalg.norm(a-b)/max(float(np.linalg.norm(b)),1e-20))


def selected_result(record,name=None):
    if name is None:
        if record.get('status')!='smoke-passed-not-spatially-qualified':raise ValueError('Need a completed traced smoke result or --run for a complete study')
        return record['result']
    if record.get('status')!='passed-periodic-nonlinear-motion-numerics-only' or name not in record.get('runs',{}):
        raise ValueError('Cannot select a missing result or recover a failed study')
    return record['runs'][name]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary',type=Path,required=True)
    parser.add_argument('--run',help='select a nonzero-velocity run from a completed full study')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('preserve the prior audit; choose a new output')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    audit_sources=capture(args.output.parent,[Path(__file__)])
    summary_sha=sha(args.summary)
    record=json.loads(args.summary.read_text())
    result=selected_result(record,args.run);work=args.summary.parent
    for source,entry in record['source_snapshots'].items():
        if sha(work/entry['snapshot'])!=entry['sha256']:raise ValueError('Changed source snapshot')
        if sha(source)!=entry['sha256']:raise ValueError('Trace physics differs from the current audit implementation')
    if not result.get('trace'):raise ValueError('Missing raw coefficient trace')
    path=work/result['trace']['file']
    if sha(path)!=result['trace']['sha256']:raise ValueError('Changed raw trace')
    material=result['material'];speed=result['speed_m_s'];steps=result['steps_per_period']
    if speed==0:raise ValueError('Use a nonzero-velocity trace for this BDF2 audit')
    plate,_,_=bias_state(material['thickness_m'],material['mu_initial'],material['saturation_polarization_t'],
                         result['depth_cells'],result['modes_per_phase'],result['angular_samples'],result['geometry'])
    wall=result['wall']
    system=Transient(plate,gap=wall['gap_m'],wall=wall['thickness_m'],conductivity=wall['conductivity_s_m'],
                     wall_cells=result['wall_cells'],gap_cells=result['gap_cells'])
    with np.load(path,allow_pickle=False) as archive:
        states=archive['states_last_two_periods'];losses=archive['loss_samples'];forces=archive['force_samples']
        work_samples=archive['source_work_samples'];dt=float(archive['dt_s'])
    if states.shape!=(2*steps,system.size) or not np.isfinite(states).all() or not np.isfinite(dt) or dt<=0:
        raise ValueError('Incomplete or nonfinite coefficient trace')
    expected_dt=1/(result['frequency_hz']*steps)
    if not np.isclose(dt,expected_dt,rtol=1e-12,atol=0):raise ValueError('Trace time base changed')
    if any(v.shape!=(2*steps,) or not np.isfinite(v).all() for v in [losses,forces,work_samples]):raise ValueError('Incomplete trace integrals')
    computed_loss=[];computed_force=[];computed_work=[];maximum_residual=0.
    for index in range(steps,2*steps):
        value=states[index];derivative=(3*value-4*states[index-1]+states[index-2])/(2*dt)
        time=(index-steps+1)*dt
        source,mechanical_derivative=moving_source(plate,speed*time)
        perturbation=np.zeros(system.size);perturbation[:plate.modes]=source-plate.incident/MU0
        gradient=system.evaluate(value,False)[1]
        residual=float(np.linalg.norm(gradient+system.mass@derivative-perturbation)/system.scale)
        if not np.isfinite(residual):raise ValueError('Nonfinite recomputed nonlinear residual')
        maximum_residual=max(maximum_residual,residual)
        computed_loss.append(float(derivative@(system.mass@derivative)))
        computed_force.append(float(mechanical_derivative@value[:plate.modes]))
        computed_work.append(float(source@derivative[:plate.modes]))
    errors={'joule_samples':relative_difference(computed_loss,losses[-steps:]),
            'force_samples':relative_difference(computed_force,forces[-steps:]),
            'source_work_samples':relative_difference(computed_work,work_samples[-steps:])}
    if maximum_residual>1e-9 or max(errors.values())>1e-6:raise ValueError('Raw trace does not satisfy its equations or recorded integrals')
    loss=float(np.mean(computed_loss));force=float(np.mean(computed_force));power=-force*speed
    balance={'drag_joule':abs(power/loss-1),'source_joule':abs(float(np.mean(computed_work))/loss-1)}
    settlement=relative_difference(states[-steps:],states[:steps])
    if max(balance.values())>0.02 or settlement>1e-5:raise ValueError('Raw trace fails periodic settlement or power gates')
    diagnostics=sampled_diagnostics(plate,states[-steps:],material['mu_initial'],material['saturation_polarization_t'])
    if sha(args.summary)!=summary_sha or sha(path)!=result['trace']['sha256']:raise ValueError('Trace inputs changed during audit')
    if sha(__file__)!=audit_sources[str(Path(__file__).resolve())]['sha256']:raise ValueError('Audit source changed during validation')
    for source,entry in record['source_snapshots'].items():
        if sha(source)!=entry['sha256']:raise ValueError('Trace physics changed during audit')
    report={'scope':__doc__,'status':'passed-internal-periodic-trace-only','source_summary_sha256':sha(args.summary),
            'trace_sha256':sha(path),'max_recomputed_relative_equation_residual':maximum_residual,
            'recorded_integral_relative_errors':errors,'power_balance_relative_errors':balance,
            'periodic_settlement_relative_change':settlement,'sampled_material_state':diagnostics,
            'source_snapshots':audit_sources}
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
