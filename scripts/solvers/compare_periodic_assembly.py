#!/usr/bin/env python3
"""Same-case automatic/explicit full nonlinear assembly consistency check.

Both whole trajectories and original automatic-energy state audits must pass.
These are implementation equivalence checks, not a new material reference or
an amplitude envelope. Initial guesses, source resolution and schedule match.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from compare_periodic_nonlinear import load,audit
from post_project_force import sha
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['automatic','explicit','automatic-audit','explicit-audit','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve prior assembly checks')
    a=load(args.automatic,'completed-independent-periodic-nonlinear-transient-unqualified');b=load(args.explicit,'completed-independent-periodic-nonlinear-transient-unqualified')
    for key in ['request','source_summary_sha256','source_bias_sha256','source_resolution','material','actual_completed_periods']:
        if a[key]!=b[key]:raise ValueError('Assembly comparison changed request, source, material or schedule')
    if b.get('nonlinear_assembly')!='explicit full gradient/tangent reassembled every iterate' and b.get('residual_evaluation')!='state difference before conducting-mass multiplication':
        raise ValueError('Not a declared alternative nonlinear assembly/residual evaluation')
    for work,proof in [(args.automatic,args.automatic_audit),(args.explicit,args.explicit_audit)]:
        audit(proof,'passed-ngsolve-midpoint-trace-equations-only',work,work/'last-two-periods.npz')
    with np.load(args.automatic/'last-two-periods.npz',allow_pickle=False) as first,np.load(args.explicit/'last-two-periods.npz',allow_pickle=False) as second:
        if not np.array_equal(first['equilibrium'],second['equilibrium']):raise ValueError('Different attached DC equilibria')
        x=first['midpoints']-first['equilibrium'];y=second['midpoints']-second['equilibrium']
        ripple=float(np.linalg.norm(x-y)/np.linalg.norm(x))
    loss=abs(a['joule_coefficient_w_m2_t2']/b['joule_coefficient_w_m2_t2']-1)
    reflection=float(np.linalg.norm(np.array(a['reflection'])-b['reflection']))
    passed=bool(np.isfinite([ripple,loss,reflection]).all() and max(ripple,loss,reflection)<=1e-6)
    output={'status':'passed-full-nonlinear-assembly-equivalence-only' if passed else 'failed','scope':__doc__,
        'relative_ripple_state_difference':ripple,'relative_loss_difference':loss,'absolute_reflection_difference':reflection,'consistency_limit':1e-6,
        'wall_seconds':{'automatic':a['seconds'],'explicit':b['seconds']},
        'input_hashes':{str(p):sha(p) for p in [args.automatic/'summary.json',args.explicit/'summary.json',args.automatic_audit,args.explicit_audit]},
        'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if not passed:raise SystemExit('Nonlinear assembly equivalence failed')


if __name__=='__main__':main()
