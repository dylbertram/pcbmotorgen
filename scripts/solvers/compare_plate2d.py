#!/usr/bin/env python3
"""Compare only completed, independently refined nonlinear planar reports."""
import argparse
import hashlib
import json
from pathlib import Path


def compare(a, b):
    for report in [a,b]:
        if report.get('status') != 'passed' or not report.get('refined') or report.get('failures'):
            raise ValueError('Only accepted refined jobs can be compared')
    if {a.get('backend'), b.get('backend')} != {'elmer','getdp'}:
        raise ValueError('Expected independent Elmer and GetDP jobs')
    if set(a['cases']) != set(b['cases']):
        raise ValueError('Material cases differ')
    differences = {}
    for label in a['cases']:
        differences[label] = {}
        for tag in ['fine','domain']:
            x,y = a['cases'][label][tag], b['cases'][label][tag]
            if x['reference'] != y['reference']:
                raise ValueError('FEMM references differ')
            for part in ['bare','plate']:
                if x[part]['sha256']['plate2d.geo'] != y[part]['sha256']['plate2d.geo']:
                    raise ValueError('Geometry source differs')
                if x[part]['sha256']['plate.msh'] != y[part]['sha256']['plate.msh']:
                    raise ValueError('Mesh differs')
            differences[label][tag] = {key:abs(x[key]/y[key]-1) for key in ['field_ratio','pressure_pa']}
    passed = all(v <= 0.02 for runs in differences.values() for values in runs.values() for v in values.values())
    return {'scope':'accepted planar nonlinear cases only; not finite 3D motion',
            'relative_differences':differences,'passed':passed}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elmer-work',type=Path,required=True)
    parser.add_argument('--getdp-work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    paths=[work/'summary.json' for work in [args.elmer_work,args.getdp_work]]
    report=compare(*(json.loads(path.read_text()) for path in paths))
    report['summary_sha256']=[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if not report['passed']:
        raise SystemExit('Cross-solver disagreement exceeds 2%')
    print('PASS: independently refined Elmer/GetDP planar fields and forces agree within 2%')


if __name__=='__main__':
    main()
