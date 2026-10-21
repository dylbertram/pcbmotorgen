#!/usr/bin/env python3
"""Check archived affine air fields against direct GetDP interior evaluations.

This audits the export/reader path, not FEM accuracy. It never changes a source
job or accepts a failed solve. Direct evaluations reuse a completed bare result
in a new directory; no matrix assembly or new material solve is requested.
"""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from check_free_space import run
from post_project_force import completed_field, sha
from read_vtu import _vector_mesh
from source_snapshot import capture


def compare(actual, expected):
    actual=np.asarray(actual,dtype=float);expected=np.asarray(expected,dtype=float)
    if actual.shape!=expected.shape or actual.ndim!=2 or actual.shape[1]!=3 or not np.isfinite([actual,expected]).all():
        raise ValueError('Expected matching finite vector samples')
    error=float(np.max(np.abs(actual-expected)))
    scale=max(1.,float(np.max(np.abs(expected))))
    return {'maximum_absolute_error_t':error,'limit_t':1e-10*scale,'passed':error<=1e-10*scale}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--getdp',type=Path,required=True)
    parser.add_argument('--output-directory',type=Path,required=True)
    args=parser.parse_args();work=args.work.resolve();output=args.output_directory.resolve()
    source,field=completed_field(work,'bare')
    if source.get('backend')!='getdp' or source.get('element_order') not in [1,2]:
        raise ValueError('Need a completed affine GetDP bare field')
    if output.exists():raise ValueError('Preserve prior export audits; choose a new directory')
    originals=[work/'summary.json',work/'project.msh',field,*[work/'bare'/('project.'+suffix) for suffix in ['pro','pre','res']]]
    hashes={str(p):sha(p) for p in originals}
    stat=field.stat();vertices,vectors,*_=_vector_mesh(str(field),stat.st_mtime_ns,stat.st_size,'magnetic flux density e')
    centres=vertices.mean(axis=1)
    model=source['model'];bottom=min(m['origin_m'][2] for m in model['magnets'])
    top=max(m['origin_m'][2]+m['size_m'][2] for m in model['magnets'])
    chosen=[]
    for plane in [bottom-0.00015,top+0.00015]:
        candidates=np.flatnonzero((np.abs(centres[:,2]-plane)<0.0001)&(centres[:,0]>0)&(centres[:,0]<0.015)&(centres[:,1]>0)&(centres[:,1]<0.0025))
        if len(candidates)<16:raise ValueError('Missing enough off-symmetry air cells near the PMs')
        chosen.extend(candidates[np.linspace(0,len(candidates)-1,16,dtype=int)])
    points=centres[chosen];expected=vectors[chosen].mean(axis=1)
    output.mkdir(parents=True)
    snapshots=capture(output,[Path(__file__),Path(__file__).parent/'read_vtu.py',Path(__file__).parent/'post_project_force.py'])
    for suffix in ['pre','res']:shutil.copy2(work/'bare'/('project.'+suffix),output/('project.'+suffix))
    text=(work/'bare/project.pro').read_text()
    operations='\n'.join(f'Print[b,OnPoint {{{p[0]:.17g},{p[1]:.17g},{p[2]:.17g}}},Format SimpleTable,File "point-{i}.txt"];' for i,p in enumerate(points))
    text+='\nPostOperation {{Name ExportAudit; NameOfPostProcessing Fields; Operation {\n'+operations+'\n}}}\n'
    (output/'project.pro').write_text(text)
    report={'status':'running','scope':__doc__,'source_hashes':hashes,'source_snapshots':snapshots,
            'getdp_executable_sha256':sha(args.getdp.resolve()),'sample_count':len(points)}
    summary=output/'summary.json';summary.write_text(json.dumps(report,indent=2)+'\n')
    try:
        elapsed=run([str(args.getdp.resolve()),'project.pro','-msh',str(work/'project.msh'),'-pos','ExportAudit','-setnumber','Mode','0','-v','4'],output,'post.log')
        actual=[]
        for i,point in enumerate(points):
            row=np.loadtxt(output/f'point-{i}.txt').reshape(-1)
            if row.shape!=(6,) or not np.isfinite(row).all():raise ValueError('Invalid direct GetDP point export')
            np.testing.assert_allclose(row[:3],point,rtol=0,atol=1e-14)
            actual.append(row[3:])
        check=compare(actual,expected)
        np.savez_compressed(output/'samples.npz',points_m=points,exported_affine_b_t=expected,direct_getdp_b_t=actual)
        for path,digest in hashes.items():
            if sha(Path(path))!=digest:raise ValueError('Original completed job changed during audit')
        report.update(status='passed-export-path-only' if check['passed'] else 'failed',comparison=check,seconds=elapsed,
                      samples_sha256=sha(output/'samples.npz'))
        if not check['passed']:raise ValueError('Direct GetDP values disagree with archived affine interpolation')
    except BaseException as error:
        report.update(status='failed',error=str(error));raise
    finally:
        summary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report['comparison'],indent=2))


if __name__=='__main__':main()
