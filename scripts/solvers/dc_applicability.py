#!/usr/bin/env python3
"""Inspect actual DC request applicability without launching any numerical job.

Re-verifies registered evidence and checks the actual host-produced copper,
explicit return and acknowledged placement. A geometry-only export is not a
qualified source or force. No force, solver command or cached force is returned.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_dc_case_matrix import Evidence
from dc_qualified_cases import read_registry,verify_case
from dc_request_contract import UnsupportedDcRequest,encoded,geometry_descriptor,check_stack_settings
from recalculate_dc_request import select_case,unchanged_request_bytes


def inspect_request(request,cases):
    result=dict(schema='finite-dc-applicability-v1',request_id=request.get('request_id'),state='unsupported',
        source_status='unqualified',force_status='unqualified',reason='',qualified_case=None)
    try:
        required={'schema','request_id','winding','material_model','return_geometry','current_a','pm_offset_x_m','placement_acknowledged'}
        encoded(request)
        if request.get('schema')!='finite-dc-live-request-v2' or set(request)!=required:
            raise UnsupportedDcRequest('Complete versioned actual-design request required')
        if not isinstance(request['request_id'],str) or not 1<=len(request['request_id'])<=128:
            raise UnsupportedDcRequest('Bounded request identity required')
        if request['placement_acknowledged'] is not True:
            raise UnsupportedDcRequest('Acknowledge the explicit placement and return before checking this design')
        for key,values in [('current_a',[0.,.1,-.1,.5,-.5]),('pm_offset_x_m',[0.,.0001,-.0001])]:
            if type(request[key]) not in [int,float] or request[key] not in values:
                raise UnsupportedDcRequest('Requested current or pose is outside the sampled qualification scope')
        actual=geometry_descriptor(request['winding'])
        if not isinstance(request['material_model'],dict) or not isinstance(request['return_geometry'],dict):
            raise UnsupportedDcRequest('Explicit material model and finite return objects required')
        if set(request['material_model'])!={'coordinate_convention','footprint_m','pcb_thickness_m','magnets','stack'} or set(request['return_geometry'])!={'return_path_m','return_width_m','return_thickness_m','drive_path_m'}:
            raise UnsupportedDcRequest('Complete physical placement and finite return fields required;an empty object is not a preparation declaration')
        check_stack_settings(actual['sim'].get('backplane'),request['material_model'])
        try:case,_=select_case(request,cases)
        except UnsupportedDcRequest as error:
            result.update(state='preparation-required',reason=str(error)+'; run the separate offline preparation and full qualification workflow before calculating force here')
        else:
            result.update(state='qualified',source_status='qualified-exact-basis',force_status='qualified-sampled-states',
                qualified_case={key:case[key] for key in ['case_id','label','audit_sha256']},
                reason='The active copper, return and placement match this verified case. Force calculation still solves fresh fields.')
    except (UnsupportedDcRequest,ValueError,KeyError,TypeError,IndexError) as error:
        result['reason']=str(error)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request',type=Path,required=True);parser.add_argument('--archive-root',type=Path,required=True)
    args=parser.parse_args();path=args.request.resolve();digest=hashlib.sha256(path.read_bytes()).hexdigest()
    request=json.loads(unchanged_request_bytes(path,digest));evidence=Evidence();root=args.archive_root.resolve()
    cases=[verify_case(root,entry,evidence) for entry in read_registry(root)['cases']]
    result=inspect_request(request,cases);result['request_sha256']=digest
    evidence.unchanged();unchanged_request_bytes(path,digest)
    print(json.dumps(result,allow_nan=False))


if __name__=='__main__':main()
