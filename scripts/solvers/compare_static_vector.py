#!/usr/bin/env python3
"""Independent B-energy/H-potential finite-material comparison at one pose.

The analytical PM particular field and provisional constitutive law are shared.
Both total and material-response fields are checked so source dominance cannot
hide response error. This alone does not qualify a vector mesh or motion.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_project_bare_map import observations
from compare_reduced_fields import completed_receipt
from ngsolve_reduced import total_field as scalar_field
from ngsolve_vector_static import total_field as vector_field
from post_project_force import sha
from reduced_potential import source_field
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scalar-work',type=Path,required=True);parser.add_argument('--vector-work',type=Path,required=True)
    parser.add_argument('--scalar-force',type=Path);parser.add_argument('--vector-force',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve earlier comparisons')
    if bool(args.scalar_force)!=bool(args.vector_force):parser.error('Force reports must be supplied together')
    a,first=scalar_field(args.scalar_work);b,second=vector_field(args.vector_work)
    completed_receipt(a);completed_receipt(b)
    if a['model']!=b['model']:raise ValueError('Different physical source/material models')
    incident=source_field(a['model']);checks={};failures=[]
    for label,points in observations(a['model'],64,24,both_sides=True).items():
        x=first(points);y=second(points);source=incident(points)
        total=float(np.linalg.norm(x-y)/np.linalg.norm(x));response=float(np.linalg.norm(x-y)/np.linalg.norm(x-source))
        checks[label]={'total_relative_error':total,'response_relative_error':response,'passed':max(total,response)<=.05}
        if not np.isfinite([total,response]).all() or max(total,response)>.05:failures.append(label)
    if args.scalar_force:
        forces=[]
        for path in [args.scalar_force,args.vector_force]:
            report=json.loads(path.read_text());completed_receipt(report)
            if report['status']!='passed-static-material-force-integration-only' or report['failures']:
                raise ValueError('Incomplete or failed static force integration')
            degree=str(max(map(int,report['levels'])));delta=str(min(map(float,report['levels'][degree])))
            forces.append(np.array(report['levels'][degree][delta]['force_n']))
        error=float(np.linalg.norm(forces[0]-forces[1]));limit=max(1e-8,.05*float(np.linalg.norm(forces[0])))
        checks['force']={'absolute_difference_n':error,'limit_n':limit,'passed':error<=limit}
        if error>limit:failures.append('force')
    output={'status':'failed' if failures else 'passed-static-vector-scalar-agreement-only','scope':__doc__,
        'source_summary_sha256':[sha(args.scalar_work/'summary.json'),sha(args.vector_work/'summary.json')],
        'gate':.05,'checks':checks,'failures':failures,'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    if failures:raise SystemExit('\n'.join(failures))


if __name__=='__main__':main()
