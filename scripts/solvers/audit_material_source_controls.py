#!/usr/bin/env python3
"""Isolated controls for exterior magnetization-source fields and PM forces.

Raw A-curl interpolation remains separate and may be unqualified. This checks
the reconstructed exterior output under unchanged2% refinement/5% reference
gates, not interior fields, differential AC or a finite motor rating.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np

from audit_static_material_controls import load,control_request,compare,force
from compare_reduced_fields import completed_receipt
from post_project_force import sha
from source_snapshot import capture


def read_field(path,work):
    report=json.loads(path.read_text());completed_receipt(report)
    archive=path.with_suffix('.npz')
    if report['status']!='passed-exterior-magnetization-field-reference-and-volume-only' or report['failures']:
        raise ValueError('Exterior source field has not passed its own volume/reference checks')
    if report['input_hashes'].get(str(work/'summary.json'))!=sha(work/'summary.json') or sha(archive)!=report['probe_archive_sha256']:
        raise ValueError('Mismatched or changed exterior field archive')
    with np.load(archive,allow_pickle=False) as data:values={k:np.array(data[k]) for k in data.files}
    return report,values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for label in ['base','mesh','domain','quadrature']:
        for suffix in ['', '-field','-force']:parser.add_argument('--'+label+suffix,type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('Preserve previous exterior output-control evidence')
    records={};fields={};reports={};forces={};hashes={}
    for label in ['base','mesh','domain','quadrature']:
        work=getattr(args,label).resolve();fp=getattr(args,label+'_field').resolve();ff=getattr(args,label+'_force').resolve()
        records[label],_=load(work);reports[label],fields[label]=read_field(fp,work);forces[label]=force(ff,work)
        for path in [work/'summary.json',fp,ff]:hashes[str(path)]=sha(path)
    output={'status':'running','scope':__doc__,'checks':{},'failures':[],'input_hashes':hashes,
        'source_snapshots':capture(args.output.parent,[Path(__file__),Path(__file__).with_name('audit_static_material_controls.py')])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):output['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    save()
    try:
        for label in ['mesh','domain','quadrature']:
            if records[label]['model']!=records['base']['model']:raise ValueError('Different physical material/source geometry')
            control_request(records['base']['request'],records[label]['request'],label);checks={}
            for i,name in enumerate(reports['base']['checks']):
                first=fields['base'];second=fields[label]
                for prefix in ['points','source_b']:
                    if not np.array_equal(first[f'{prefix}_{i}'],second[f'{prefix}_{i}']):raise ValueError('Different observation/source maps')
                checks[name]=compare(first[f'fine_reconstructed_b_{i}'],second[f'fine_reconstructed_b_{i}'],first[f'source_b_{i}'],.02)
                if not checks[name]['passed']:output['failures'].append(label+'/'+name)
            error=float(np.linalg.norm(forces['base']-forces[label]));limit=max(1e-8,.02*float(np.linalg.norm(forces['base'])))
            checks['force']={'absolute_change_n':error,'limit_n':limit,'passed':error<=limit}
            if error>limit:output['failures'].append(label+'/force')
            output['checks'][label]=checks;save()
        for path,digest in hashes.items():
            if sha(Path(path))!=digest:raise ValueError('Exterior-control input changed')
        for path,entry in output['source_snapshots'].items():
            if sha(Path(path))!=entry['sha256']:raise ValueError('Exterior-control implementation changed')
        output['status']='failed' if output['failures'] else 'passed-exterior-source-field-and-force-static-controls-only';save()
        if output['failures']:raise ValueError('\n'.join(output['failures']))
    except BaseException as error:
        output.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
