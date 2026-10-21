#!/usr/bin/env python3
"""Inspect ideal-wire contact with the declared magnetic material geometry.

This audits nominal centreline geometry, not actual copper surfaces or hardware
clearance. A positive-length filament on/inside a magnetic body prevents
interpreting fixed-mesh current-difference convergence as finite-source
differential inductance qualification. No source radius or gap is fitted.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from post_project_force import sha
from source_snapshot import capture


def clip_segment(a,b,low,high):
    lower=0.;upper=1.;delta=b-a
    for axis in range(3):
        if delta[axis]==0:
            if not low[axis]<=a[axis]<=high[axis]:return None
        else:
            u=(low[axis]-a[axis])/delta[axis];v=(high[axis]-a[axis])/delta[axis]
            lower=max(lower,min(u,v));upper=min(upper,max(u,v))
            if lower>upper:return None
    return lower,upper


def contacts(segments,currents,model):
    segments=np.asarray(segments,dtype=float);currents=np.asarray(currents,dtype=float)
    if segments.ndim!=3 or segments.shape[1:]!=(2,3) or currents.shape!=(len(segments),) or not np.isfinite(segments).all() or not np.isfinite(currents).all():
        raise ValueError('Invalid ideal-wire contact geometry')
    result={}
    for material in model['stack']:
        if material['mu_r']<=1:continue
        low=np.asarray(material['origin_m']);size=np.asarray(material['size_m']);high=low+size
        if low.shape!=(3,) or size.shape!=(3,) or not np.isfinite([low,size]).all() or np.min(size)<=0:raise ValueError('Invalid magnetic body')
        summary={'boundary_segments':0,'interior_segments':0,'point_contacts':0,'boundary_length_m':0.,'interior_length_m':0.,
            'boundary_abs_current_length_a_m':0.,'interior_abs_current_length_a_m':0.}
        for (a,b),current in zip(segments,currents):
            if current==0:continue
            clipped=clip_segment(a,b,low,high)
            if clipped is None:continue
            first,last=clipped;length=(last-first)*float(np.linalg.norm(b-a))
            if length==0:summary['point_contacts']+=1;continue
            middle=a+.5*(first+last)*(b-a);name='interior' if np.all((middle>low)&(middle<high)) else 'boundary'
            summary[name+'_segments']+=1;summary[name+'_length_m']+=length
            summary[name+'_abs_current_length_a_m']+=abs(float(current))*length
        result[material['name']]=summary
    return result


def material_inductance_resolved(contact_map):
    return not any(x['boundary_length_m']>0 or x['interior_length_m']>0 for x in contact_map.values())


def main():
    from audit_winding_reciprocity import load
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous contact-scope audits')
    report=load(args.work)
    with np.load(args.work/'closed-wire-source.npz',allow_pickle=False) as wire:result=contacts(wire['segments_m'],wire['current_per_line_amp'],report['model'])
    output={'status':'completed-ideal-wire-material-contact-scope-audit-only','scope':__doc__,'contacts':result,
        'finite_source_inductance_required':not material_inductance_resolved(result),
        'summary_sha256':sha(args.work/'summary.json'),'wire_source_sha256':report['wire_source_sha256'],
        'source_snapshots':capture(args.output.parent,[Path(__file__)])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
