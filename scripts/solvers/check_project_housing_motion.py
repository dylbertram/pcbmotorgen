#!/usr/bin/env python3
"""Real exported project winding + housing-motion integration, not a fixture lookup.

Reads a hash-verified routed-copper export already independently audited by
the winding oracle. Recalculates electrical quantities and fixed-phase force
from its actual RoutingResult and conductor heights through the current Rust
entrypoint. A new, explicit housing scenario is added to the free-space source;
root projects are never rewritten. Optional PCB-depth alignment is a declared
derived verification case, NOT a silent production geometry correction.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np

from post_project_force import sha
from source_snapshot import capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['fixture','fixture-summary','project','binary','work']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-proof',type=Path,help='links a free-space-only derived export to its original project')
    parser.add_argument('--align-pcb-to-copper',action='store_true',help='explicit derived test only; first verifies the original overlapping scenario is rejected')
    parser.add_argument('--material',choices=['aluminum6061','aluminum5052','stainless304','stainless316'],default='aluminum6061')
    parser.add_argument('--magnet-count',type=int);args=parser.parse_args();work=args.work.resolve()
    if work.exists():parser.error('Preserve previous project integration evidence')
    fixture=args.fixture.resolve();summary=args.fixture_summary.resolve();project=args.project.resolve();binary=args.binary.resolve()
    exported=json.loads(summary.read_text())
    if not exported['status'].startswith('passed') or exported['failures']:raise ValueError('Need a passed original winding export audit')
    level=next((v for v in exported['levels'].values() if v['fixture_sha256']==sha(fixture)),None)
    if level is None:raise ValueError('Actual winding fixture changed or belongs to a different export')
    if args.source_proof:
        proof=json.loads(args.source_proof.read_text())
        if proof['source_project_sha256']!=sha(project) or proof['derived_project_sha256']!=exported['project_sha256'] or proof['copper_audit_sha256']!=sha(summary):
            raise ValueError('Free-space derived export no longer matches original project')
    elif exported['project_sha256']!=sha(project):raise ValueError('Root project differs from actual winding export')
    source=json.loads(fixture.read_text());case={k:copy.deepcopy(source[k]) for k in ['sim','routing','drive','geometry_hints']}
    if case['sim']['backplane'] is not None:raise ValueError('Need the archived bare-copper source; housing is a separate explicit scenario')
    case['sim']['backplane']={'layers':[],'housing':{'material':args.material,'thickness_m':.001,'gap_m':.0001}}
    case.update(speed_m_s=3.,duration_s=.1)
    if args.magnet_count is not None:case['sim']['magnet_count']=args.magnet_count
    work.mkdir(parents=True);started=time.monotonic();root=Path(__file__).resolve().parents[2]
    hashes={str(p):sha(p) for p in [fixture,summary,project,binary]}
    if args.source_proof:hashes[str(args.source_proof.resolve())]=sha(args.source_proof)
    report={'status':'running','scope':__doc__,'input_hashes':hashes,'source_version_index':exported['version_index'],
        'explicit_scenario':{'housing':case['sim']['backplane']['housing'],'magnet_count':case['sim']['magnet_count'],'speed_m_s':3.,'duration_s':.1},
        'source_snapshots':capture(work,[Path(__file__),root/'crates/pcbmotorgen-simulation/examples/housing_motion_dump.rs'])}
    if os.environ.get('PCB_MOTOR_COMMAND_RECEIPT'):report['command_receipt']=os.environ['PCB_MOTOR_COMMAND_RECEIPT']
    def save():(work/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    def invoke(label,value):
        path=work/(label+'.input.json');path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
        result=subprocess.run([str(binary),str(path)],capture_output=True,text=True,timeout=180)
        (work/(label+'.stdout.json')).write_text(result.stdout);(work/(label+'.stderr.log')).write_text(result.stderr)
        return result
    save()
    try:
        depths=case['geometry_hints']['layer_z_m'];extent=max([-z for z in depths],default=case['sim']['pcb_thickness_m'])
        if extent>case['sim']['pcb_thickness_m']+1e-9:
            rejected=invoke('original-depth-housing-rejected',case)
            if rejected.returncode==0 or 'below the first magnetic/conducting stack surface' not in rejected.stderr:
                raise ValueError('Original overlapping stack was not rejected for the intended geometry reason')
            report['original_stack_rejection']='Verified: no force/heat fallback, explicit conductor depths preserved'
            if not args.align_pcb_to_copper:raise ValueError('Explicit derived PCB-depth alignment flag required for positive verification scenario')
            report['explicit_pcb_depth_change_m']=[case['sim']['pcb_thickness_m'],extent]
            case['sim']['pcb_thickness_m']=extent;save()
        result=invoke('current-routed-project',case)
        if result.returncode:raise ValueError('Actual routed project calculation failed; see archived stderr')
        value=json.loads(result.stdout)
        if value['status']!='experimental' or 'routing_check' not in value:raise ValueError('No real routed-copper/housing estimate returned')
        routed=value['routing_check'];estimate=value['estimate']
        if routed['layer_z_m']!=depths:raise ValueError('Imported physical depths were altered')
        resistance_reference={net['net']:net['rust_resistance_ohm'] for net in source['networks']}
        checks={}
        for phase in routed['phases']:
            error=abs(phase['resistance_hot_ohm']/resistance_reference[phase['net']]-1)
            checks[phase['net']]={'relative_resistance_change':error,'passed':bool(error<=1e-9 and phase['connected'])}
        if not checks or not all(c['passed'] for c in checks.values()):raise ValueError('Current app changed actual winding graph resistance/continuity')
        housing=routed['housing_motion_from_driver']
        if housing['status']!='experimental' or abs(housing['estimate']['housing_joule_power_w']/estimate['housing_joule_power_w']-1)>1e-12:
            raise ValueError('Driver path and core housing path disagree')
        forces=np.asarray(routed['force_x_n']);old=np.asarray(source['rust_force_x_n'])
        report['force_reference_scope']='Actual fixed-phase finite PM/copper analytical calculation; not full nonlinear FEM or a hardware rating'
        if args.material.startswith('aluminum') and args.magnet_count is None:
            if not np.allclose(routed['force_positions_m'],source['force_positions_m'],rtol=0,atol=1e-9):raise ValueError('Force pose frame changed')
            error=float(np.linalg.norm(forces-old)/max(np.linalg.norm(old),1e-8));report['archived_oracle_force_relative_change']=error
            if error>.02:raise ValueError('Actual winding fixed-phase force changed beyond2% mesh/reference consistency')
        report.update(routing_checks=checks,result=value,segments=routed['segments'],vias=routed['vias'])
        for p,digest in hashes.items():
            if sha(Path(p))!=digest:raise ValueError('Project/export/binary changed during integration run')
        report.update(status='passed-real-project-routing-housing-integration-only',seconds=time.monotonic()-started);save()
        print(report['status'],checks,flush=True)
    except BaseException as error:
        report.update(status='failed',error=str(error),seconds=time.monotonic()-started);save();raise


if __name__=='__main__':main()
