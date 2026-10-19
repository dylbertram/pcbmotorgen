#!/usr/bin/env python3
"""Reprocess a completed saved-project case without accepting a failed batch.

Uses the original archived raw air field, a rectangular six-face surface and
explicit quadrature. Does not recover unfinished nonlinear jobs or rescale B.
"""
import argparse
import hashlib
import json
from pathlib import Path

from maxwell_stress import box_faces, force
from read_vtu import sample_vector
from project_symmetry import mirrored_sample


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def completed_field(work, mode):
    source=json.loads((work/'summary.json').read_text())
    if source.get('status') not in ['comparison-only','completed-bare-field-only-unqualified'] or source.get('failures')!=[]:
        raise ValueError('Cannot recover an unfinished or failed project study')
    if source['status']=='completed-bare-field-only-unqualified' and mode!='bare':
        raise ValueError('Bare-only control has no qualified material field')
    if sha(work/'project.msh')!=source.get('mesh_sha256'):
        raise ValueError('Original project mesh changed or lacks a completed hash')
    result=source['runs'][mode];job=work/mode
    receipt=json.loads((job/'solve.log.command.json').read_text())
    if receipt.get('status')!='completed' or receipt.get('exit_code')!=0:
        raise ValueError('Cannot recover an incomplete/failed solver case')
    if (job/'air.pos').exists():
        field=job/'air.pos';formulation=job/'project.pro'
        field_hash=result['air_field_sha256'];formulation_hash=result['formulation_sha256']
    else:
        fields=list(job.glob('**/fields*.vtu'))
        if len(fields)!=1:raise ValueError('Missing or ambiguous vector field')
        field=fields[0];formulation=job/'case.sif'
        field_hash=result.get('air_field_sha256',result.get('vtu_sha256'))
        formulation_hash=result.get('formulation_sha256',result.get('sif_sha256'))
    if sha(field)!=field_hash or sha(formulation)!=formulation_hash:
        raise ValueError('Original field or formulation changed')
    return source,field


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--case',required=True,choices=['bare','stack'])
    parser.add_argument('--subdivisions',type=int,nargs='+',default=[64,128])
    args=parser.parse_args();work=args.work.resolve()
    if not args.subdivisions or any(not 2<=n<=512 for n in args.subdivisions):parser.error('subdivisions must be between 2 and 512')
    source,field=completed_field(work,args.case);model=source['model']
    if not model['stack']:parser.error('project has no finite stack to enclose')
    length,width=model['footprint_m'];bottom=min(o['origin_m'][2] for o in model['stack'])
    for n in args.subdivisions:
        output=work/args.case/f'force-rect-n{n}.json'
        if output.exists():raise ValueError(f'Preserve the existing report: {output}')
        report={'scope':__doc__,'status':'running','case':args.case,'subdivisions':n,'surfaces':{},
                 'source_summary_sha256':sha(work/'summary.json'),'raw_field_sha256':sha(field),
                 'quarter_symmetry':bool(source.get('quarter_symmetry',False)),
                'analysis_sha256':sha(Path(__file__))}
        output.write_text(json.dumps(report,indent=2)+'\n')
        for clearance in [0.0001,0.0002,0.0003]:
            faces=box_faces(length/2+clearance,bottom-clearance,clearance,n,halfdepth=width/2+clearance)
            reader=mirrored_sample if source.get('quarter_symmetry',False) else sample_vector
            fields=[reader(field,points,'magnetic flux density e') for points,_,_ in faces]
            vector=force(faces,fields).tolist();report['surfaces'][str(clearance)]=vector
            print(args.case,n,clearance,vector,flush=True)
        report['status']='comparison-only'
        output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
