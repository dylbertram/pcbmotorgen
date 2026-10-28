#!/usr/bin/env python3
"""Reprocess completed finite-plate solutions on closed air surfaces.

No re-solve or material fit. GetDP uses the archived .pre/.res and unchanged
formulation with appended air-field export. Elmer uses raw element B from the
archived VTU, not a nodal field smoothed across material interfaces. Surface,
mesh and independent-backend gates must pass before this is a design result.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from check_free_space import run
from maxwell_stress import box_faces, force
from read_vtu import sample_vector


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',required=True,type=Path)
    parser.add_argument('--getdp',type=Path)
    parser.add_argument('--summary',default='summary.json',help='archived source report within --work')
    parser.add_argument('--elmer-field',choices=['element','nodal'],default='element',help='raw element B avoids smoothing across material interfaces')
    parser.add_argument('--subdivisions',type=int,default=32)
    args=parser.parse_args()
    if args.subdivisions<8:
        parser.error('at least 8 subdivisions per face are required')
    work=args.work.resolve()
    source_path=work/args.summary
    source=json.loads(source_path.read_text())
    if source.get('status') not in ['comparison-only','passed'] or source.get('failures'):
        parser.error('requires a completed finite-plate comparison without failed field gates')
    request=source['request']
    if request['backend']=='getdp' and not args.getdp:
        parser.error('--getdp is required for GetDP solution reprocessing')
    if request['backend'] not in ['elmer','getdp']:
        parser.error('unknown finite-plate backend')
    report={'scope':'finite 3D magnetostatic plate force only; no motion/current solve','status':'running',
            'backend':request['backend'],'subdivisions':args.subdivisions,'source_summary_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
            'air_field_sha256':{},'surfaces':{str(c):{} for c in [0.0004,0.0006,0.0008]}}
    report['field_representation']=args.elmer_field if request['backend']=='elmer' else 'raw air tetrahedra'
    prefix='force-element' if request['backend']=='elmer' and args.elmer_field=='element' else 'force'
    output=work/f'{prefix}-n{args.subdivisions}.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    for mode,name in enumerate(['bare','linear','nonlinear']):
        job=work/name
        if request['backend']=='getdp':
            destination=job/'raw-air-force'
            destination.mkdir(exist_ok=True)
            formulation=(job/'finite_plate.pro').read_text()
            raw='''PostOperation {{Name RawAir; NameOfPostProcessing Fields; Operation {
Print[b,OnElementsOf Air,Format Gmsh,File "air.pos"];
}}}
'''
            (destination/'finite_plate.pro').write_text(formulation+'\n'+raw)
            for suffix in ['pre','res']:
                shutil.copyfile(job/f'finite_plate.{suffix}',destination/f'finite_plate.{suffix}')
            # The same constraints, basis and mode are necessary to load .res.
            run([str(args.getdp.resolve()),'finite_plate.pro','-msh',str(job/'plate.msh'),'-pos','RawAir','-v','4',
                 '-setnumber','Mu',str(request['mu']),'-setnumber','Bsat',str(request['bsat']),'-setnumber','Mode',str(mode),
                 '-setnumber','Relaxation',str(request.get('relaxation',0.7))],destination,'post.log')
            air=destination/'air.pos'
        else:
            files=list(job.glob('**/fields*.vtu'))
            assert len(files)==1,files
            air=files[0]
        report['air_field_sha256'][name]=hashlib.sha256(air.read_bytes()).hexdigest()
        for clearance in [0.0004,0.0006,0.0008]:
            faces=box_faces(0.006+clearance,-request['thickness']-clearance,clearance,args.subdivisions)
            field_name='magnetic flux density e' if request['backend']=='elmer' and args.elmer_field=='element' else 'magnetic flux density'
            fields=[sample_vector(air,points,name=field_name) for points,_,_ in faces]
            result=force(faces,fields).tolist()
            report['surfaces'][str(clearance)][name]=result
            print(name,'clearance',clearance,'force N',result,flush=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
    report['status']='comparison-only'
    output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
