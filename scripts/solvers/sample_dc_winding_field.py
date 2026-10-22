#!/usr/bin/env python3
"""Fresh exterior B of an exact registered finite-copper DC source.

Reuses only an audited affine-RT0 current basis. Integrates the actual finite
cells directly at newly declared observations, including the declared return.
No magnets, material reaction, filament substitution, source/force solve or
registry admission. A new display grid is not new field-refinement evidence.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from audit_dc_case_matrix import Evidence
from dc_applicability import inspect_request
from dc_qualified_cases import read_registry,resolve,verify_case
from finite_tetra_current_field import tetrahedron_field
from recalculate_dc_request import select_case,unchanged_request_bytes
from source_snapshot import capture


def observations(sampling):
    if not isinstance(sampling,dict) or set(sampling)!={'bounds_m','counts'}:raise ValueError('Explicit XYZ sampling required')
    bounds=np.asarray(sampling['bounds_m'],dtype=float);counts=sampling['counts']
    if bounds.shape!=(3,2) or not np.isfinite(bounds).all() or np.any(abs(bounds)>1) or np.any(bounds[:,0]>=bounds[:,1]):
        raise ValueError('Finite ordered observation bounds within one metre required')
    if not isinstance(counts,list) or len(counts)!=3 or any(type(n) is not int or not 2<=n<=16 for n in counts) or np.prod(counts)>96:
        raise ValueError('Direct finite-copper sampling is capped at 96 observations, 2..16 per axis')
    axes=[np.linspace(*bounds[i],counts[i]) for i in range(3)]
    return np.asarray([[x,y,z] for z in axes[2] for y in axes[1] for x in axes[0]])


def integrate(points,cells,mean,slope,basis_current,requested_current):
    if not np.isfinite(basis_current) or basis_current<=0 or requested_current not in [0.,.1,-.1,.5,-.5]:
        raise ValueError('Own finite source normalization and a sampled signed loop current required')
    # Even zero-current requests retain exterior ownership checks. No source
    # radius, point relocation or artificial softening is applied.
    return tetrahedron_field(points,cells,mean,radial_slope=slope)*(requested_current/basis_current)


def bound_declaration(evidence,path):
    path=Path(path).resolve()
    if path not in evidence.hashes:raise ValueError('Physical declaration is not bound to case evidence')
    evidence.unchanged()
    # A hash-bound physical declaration is not necessarily a solver report and
    # need not have a command_receipt. Qualification comes from its case audit.
    return json.loads(path.read_text())


def sample_request(request_path,root,work):
    evidence=Evidence();digest=evidence.digest(request_path)
    implementations=[Path(__file__),*[Path(__file__).with_name(name) for name in ['finite_tetra_current_field.py',
        'dc_qualified_cases.py','dc_request_contract.py','dc_applicability.py','recalculate_dc_request.py','audit_dc_case_matrix.py']]]
    for path in implementations:evidence.digest(path)
    request=json.loads(unchanged_request_bytes(request_path,digest))
    if set(request)!={'schema','request_id','dc_request','sampling'} or request['schema']!='qualified-dc-winding-field-request-v1':
        raise ValueError('Versioned actual-design winding-field request required')
    dc=request['dc_request'];points=observations(request['sampling'])
    if request['request_id']!=dc['request_id']:raise ValueError('Field and actual-design request identities differ')
    entries=read_registry(root)['cases'];cases=[verify_case(root,entry,evidence) for entry in entries]
    applicability=inspect_request(dc,cases)
    if applicability['state']!='qualified':raise ValueError(applicability['reason'])
    case,eligibility=select_case(dc,cases)
    entry=next(e for e in entries if e['case_id']==case['case_id'])
    source_path=resolve(root,entry['source'])/'summary.json';source=evidence.report(source_path)
    current=evidence.report(Path(source['source_work'])/'summary.json')
    geometry_paths=[Path(p).with_name('summary.json') for p in current['input_hashes'] if p.endswith('/copper.brep')]
    if len(geometry_paths)!=1:raise ValueError('Unique bound finite-copper coordinate transform required')
    geometry_path=geometry_paths[0]
    expected_geometry=evidence.hashes.get(geometry_path.resolve())
    if not expected_geometry or evidence.digest(geometry_path)!=expected_geometry:raise ValueError('Copper transform is not bound to case evidence')
    geometry=evidence.report(geometry_path)
    shift=np.asarray(geometry['translation_m'],dtype=float)
    if shift.shape!=(3,) or not np.isfinite(shift).all():raise ValueError('Invalid actual source coordinate transform')
    archive=source_path.with_name('rt0-source.npz')
    if evidence.digest(archive)!=source['archive_sha256']:raise ValueError('Actual finite-current archive changed')
    # Verify all evidence before allocating source arrays or evaluating a field.
    evidence.unchanged();unchanged_request_bytes(request_path,digest)
    with np.load(archive,allow_pickle=False) as saved:
        cells=saved['vertices_m'][saved['cells']];mean=saved['mean_current_a_m2'];slope=saved['radial_slope_a_m3']
    value=integrate(points+shift,cells,mean,slope,source['effective_loop_current_a'],dc['current_a'])
    if not np.isfinite(value).all():raise ValueError('Nonfinite winding field; no display returned')
    # Driven phases belong to the audited source, not free viewer assumptions.
    phases={}
    if geometry.get('actual_study_work'):
        study_path=Path(geometry['actual_study_work'])/'summary.json'
        expected_study=evidence.hashes.get(study_path.resolve())
        if not expected_study or evidence.digest(study_path)!=expected_study:raise ValueError('Driven phase configuration is not audited')
        study=bound_declaration(evidence,study_path)
        phases={name:phase['current_a']*dc['current_a'] for name,phase in study['closure']['phase_data'].items()}
    evidence.unchanged();unchanged_request_bytes(request_path,digest)
    if work.exists():raise ValueError('Fresh field result directory required')
    work.mkdir(parents=True)
    snapshots=capture(work,implementations)
    report=dict(status='sampled-qualified-finite-copper-winding-field-only',request_id=request['request_id'],
        input_request_sha256=digest,qualified_case=applicability['qualified_case'],sampling=request['sampling'],
        loop_current_a=dc['current_a'],source_basis_sha256=evidence.digest(source_path),source_translation_m=shift.tolist(),
        scope=__doc__,source_elements=int(len(cells)),phase_currents_a=phases,
        field=dict(method='qualified-finite-copper-winding-xyz',scope=__doc__,magnets=[],samples=[
            dict(position_m=p.tolist(),b_t=b.tolist(),magnitude_t=float(np.linalg.norm(b))) for p,b in zip(points,value)]),
        evidence_hashes={str(p):h for p,h in evidence.hashes.items()},source_snapshots=snapshots)
    (work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['request','archive-root','work']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();sample_request(args.request.resolve(),args.archive_root.resolve(),args.work.resolve())


if __name__=='__main__':main()
