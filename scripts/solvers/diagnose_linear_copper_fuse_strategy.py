#!/usr/bin/env python3
"""Compare Boolean fuse groupings of the unchanged declared copper primitives.

Diagnostic only: the same build pieces are fused in different orders and each
result is compared with the analytic declared union. Grouping changes no
dimension, position or connectivity. No CAD from this run is used downstream.
"""
import argparse
import json
from pathlib import Path
import time

from audit_copper_union_volume import union_estimate
from diagnose_linear_copper_fuse_loss import build_groups,LOSS_GATE
from finite_copper_geometry import fuse_all


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-work',type=Path,required=True);parser.add_argument('--copper-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous diagnostics')
    fixture=json.loads((args.study_work.resolve()/'fixture.json').read_text())
    shift=json.loads((args.copper_work.resolve()/'summary.json').read_text())['translation_m']
    pieces,groups,analytic=build_groups(fixture,shift)
    expected,error=union_estimate(analytic,[],3000)
    def key_network(g):return g['label'].split(':')[1] if g['label'].startswith('trace:') else 'via'
    def key_layer(g):
        if g['label'].startswith('pad:'):return 'pad:'+g['label'].split(':')[-1]
        if g['label'].startswith('barrel:'):return 'barrel'
        return 'trace'
    def grouped(key):
        names=sorted({key(g) for g in groups});parts=[]
        for name in names:parts.append(fuse_all([p for p,g in zip(pieces,groups) if key(g)==name]))
        return fuse_all(parts),{name:float(part.mass) for name,part in zip(names,parts)}
    def sequential():
        shape=pieces[0]
        for piece in pieces[1:]:shape=shape+piece
        return shape,{}
    report=dict(scope=__doc__,analytic_union_m3=expected,analytic_standard_error_m3=error,loss_gate=LOSS_GATE,strategies={})
    for name,builder in [('per-network-then-vias',lambda:grouped(key_network)),('per-kind',lambda:grouped(key_layer)),('sequential',sequential)]:
        started=time.monotonic()
        try:
            shape,parts=builder();volume=float(shape.mass)
            report['strategies'][name]=dict(volume_m3=volume,solids=len(shape.solids),relative_difference=abs(volume/expected-1),
                faithful=bool(abs(volume/expected-1)<=LOSS_GATE and len(shape.solids)==1),parts_m3=parts,seconds=time.monotonic()-started)
        except Exception as failure:
            report['strategies'][name]=dict(error=str(failure),seconds=time.monotonic()-started)
        print(name,report['strategies'][name],flush=True)
        with open(str(args.output)+'.partial','w') as stream:stream.write(json.dumps(report,indent=2)+'\n')
    with args.output.open('x') as stream:stream.write(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
