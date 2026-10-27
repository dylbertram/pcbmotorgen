#!/usr/bin/env python3
"""Compare finite FE electric-potential closure with independent resistor grids.

Both solve the same prescribed-PM low-Rm limit. This does not qualify induced
magnetic reaction, finite-speed drag, nonlinear backplanes or transient memory.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_current_closure import load
from compare_reduced_fields import field_case
from post_project_force import sha
from reduced_potential import source_field
from source_snapshot import capture
from weak_motion import solve


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work',type=Path,required=True);parser.add_argument('--closure-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous independent closure comparisons')
    closure=load(args.closure_work);report,_,_,_=field_case(args.source_work)
    if sha(args.source_work/'summary.json')!=closure['source_summary_sha256']:
        raise ValueError('Different source model for independent closure')
    archived_housing=[m for m in report['model']['stack'] if m['name']=='housing']
    if archived_housing!=[closure['housing']]:raise ValueError('Housing differs from the archived source geometry')
    housing=closure['housing'];low=np.array(housing['origin_m']);size=np.array(housing['size_m'])
    centre=low+size/2;top=np.r_[centre[:2],low[2]+size[2]]
    # Proper +90-degree rotation: the grid's +x radial slit becomes the FE
    # geometry's +y slit. B is axial, so a reflection cannot replace this.
    rotation=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    physical_source=source_field(report['model'])
    def field(points):return physical_source(points@rotation.T+top)@rotation
    velocity=np.array([closure['speed_m_s'],0.,0.])@rotation
    dimensions=size[[1,0,2]];finest=min(closure['levels'],key=float)
    snapshots=capture(args.output.parent,[Path(__file__),Path(__file__).with_name('weak_motion.py')])
    output={'status':'running','scope':__doc__,'closure_report_sha256':sha(args.closure_work/'summary.json'),
        'source_summary_sha256':sha(args.source_work/'summary.json'),'source_snapshots':snapshots,
        'rotation_grid_to_physical':rotation.tolist(),'runs':{},'checks':{},'failures':[]}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for name,slot in [('closed',0.),('slotted',.0005)]:
            runs=[]
            for n,nz in [(24,3),(36,4),(48,6)]:
                result=solve([n,3*n,nz],dimensions,velocity,closure['sigma_s_m'],field,slot)
                result['force_physical_n']=(np.array(result['force_on_conductor_n'])@rotation.T).tolist()
                runs.append(result);output['runs'][name]=runs;save();print(name,n,result['joule_power_w'],flush=True)
            fine=runs[-1];prior=runs[-2];reference=closure['levels'][finest][name]['forward']
            checks={
                'loss_refinement':abs(prior['joule_power_w']/fine['joule_power_w']-1),
                'force_refinement':float(np.linalg.norm(np.array(prior['force_physical_n'])-fine['force_physical_n'])/np.linalg.norm(fine['force_physical_n'])),
                'loss_agreement':abs(fine['joule_power_w']/reference['joule_power_w']-1),
                'force_agreement':float(np.linalg.norm(np.array(fine['force_physical_n'])-reference['housing_force_n'])/np.linalg.norm(reference['housing_force_n'])),
                'volume_agreement':abs(fine['conductor_volume_m3']/reference['volume_m3']-1)}
            output['checks'][name]=checks
            for key,error in checks.items():
                limit=.02 if 'refinement' in key else 1e-10 if key=='volume_agreement' else .05
                if not np.isfinite(error) or error>limit:output['failures'].append(name+'/'+key)
        for name,entry in snapshots.items():
            if sha(Path(name))!=entry['sha256']:raise ValueError('Independent closure implementation changed')
        if sha(args.closure_work/'summary.json')!=output['closure_report_sha256']:
            raise ValueError('FE closure report changed')
        output['status']='failed' if output['failures'] else 'passed-independent-finite-current-closure-low-rm-only'
        save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
