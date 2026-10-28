#!/usr/bin/env python3
"""Read-only exact BRep partition diagnostics; never repairs or admits geometry."""
import argparse
import json
from pathlib import Path

import numpy as np

from post_project_force import sha


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous diagnostics')
    work=args.work.resolve();summary=json.loads((work/'summary.json').read_text())
    study=Path(summary['actual_study_work'])/'summary.json';model=json.loads(study.read_text())['model']
    from netgen.occ import OCCGeometry,Box,Pnt
    inputs={str(p):sha(p) for p in [work/'summary.json',study,work/'copper.brep',work/'closed-copper-for-partition-audit.brep',Path(__file__).resolve()]}
    report=dict(status='diagnostic-only-no-qualification',input_hashes=inputs,checks=[])
    for file in ['copper.brep','closed-copper-for-partition-audit.brep']:
        try:copper=OCCGeometry(str(work/file)).shape
        except Exception as error:
            value=dict(file=file,reload_error=str(error));report['checks'].append(value)
            print(json.dumps(value),flush=True);args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');continue
        for item in model['stack']+model['magnets']:
            region=Box(Pnt(*item['origin_m']),Pnt(*(np.asarray(item['origin_m'])+item['size_m'])))
            value=dict(file=file,region=item['name'],solids=len(copper.solids),faces=len(copper.faces),volume_m3=float(copper.mass))
            try:value['distance_m']=float(copper.Distance(region))
            except Exception as error:value['distance_error']=str(error)
            try:value['overlap_m3']=float((copper*region).mass)
            except Exception as error:value['intersection_error']=str(error)
            report['checks'].append(value);print(json.dumps(value),flush=True)
            args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    for name,digest in inputs.items():
        if sha(Path(name))!=digest:raise ValueError('Diagnostic input changed')


if __name__=='__main__':main()
