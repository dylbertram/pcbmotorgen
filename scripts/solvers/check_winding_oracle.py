#!/usr/bin/env python3
"""Export actual Rust winding samples, then independently reconstruct and check.

Only prescribed-PM free space and a saved project's explicit drive/copper
settings, or the explicit DRV8311 fixture. Normal runs use fixed phase A; the
driver fixture uses exported model excitation, not an independently validated
controller waveform. Does not qualify a backplane, winding return
fan-out, finite-current closure, nonlinear material physics or hardware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import magpylib
import numpy as np
import scipy

from check_free_space import run
from source_snapshot import capture
from winding_oracle import resistances,unit_currents,conductor_samples


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path)
    parser.add_argument('--driver-reference',action='store_true',help='explicit generated DRV8311 geometry/copper case; excitation is exported, not independently controller-validated')
    parser.add_argument('--version',type=int,default=0)
    parser.add_argument('--meshes',type=int,nargs='+',default=[10,20,40,80])
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    if args.driver_reference and args.project:parser.error('driver reference and saved project are separate inputs')
    if len(args.meshes)<2 or any(not 1<=n<=512 for n in args.meshes) or any(a>=b for a,b in zip(args.meshes,args.meshes[1:])):
        parser.error('at least two increasing conductor quadrature levels in [1,512] required')
    root=Path(__file__).resolve().parents[2];work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    if any(work.iterdir()):parser.error('preserve previous studies; use an empty output directory')
    project=args.project.resolve() if args.project else None
    sources=capture(work,[Path(__file__),root/'scripts/validate_magpylib.py',Path(__file__).parent/'winding_oracle.py',
        Path(__file__).parent/'check_free_space.py',root/'crates/pcbmotorgen-simulation/src/drive/geometry.rs',
        root/'crates/pcbmotorgen-simulation/src/drive/mod.rs',root/'crates/pcbmotorgen-simulation/src/magnetic/force_eval/mod.rs',
        root/'app/desktop/src-tauri/src/commands/physics.rs',
        root/'crates/pcbmotorgen-routing/src/patterns/infinity/mod.rs',
        root/'crates/pcbmotorgen-routing/src/patterns/infinity/four_layer.rs',
        root/'crates/pcbmotorgen-routing/src/patterns/infinity/stacked.rs',
        root/'crates/pcbmotorgen-routing/src/context.rs',
        root/'app/desktop/src-tauri/src/config/bridges.rs',
        root/'crates/pcbmotorgen-dfm/src/series_vias.rs',
        Path(__file__).parent/'prescribed_pm_oracle.py',
        root/'crates/pcbmotorgen-simulation/src/magnetic/force_eval/commutation.rs'])
    report={'scope':__doc__,'status':'running','project':str(project) if project else None,'version_index':args.version,
            'driver_reference_requested':args.driver_reference,
            'project_sha256':sha(project) if project else None,'source_snapshots':sources,'levels':{},'refinements':{},'failures':[],
            'runtime':{'magpylib':magpylib.__version__,'numpy':np.__version__,'scipy':scipy.__version__}}
    output=work/'summary.json'
    def save():output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();previous=None
    try:
        for n in args.meshes:
            folder=work/f'mesh-{n}';folder.mkdir();fixture=folder/'fixture.json'
            os.environ['PCB_MOTOR_ORACLE_OUTPUT']=str(fixture);os.environ['PCB_MOTOR_FORCE_MESH']=str(n)
            if args.driver_reference:os.environ['PCB_MOTOR_ORACLE_CASE']='drv8311'
            else:os.environ.pop('PCB_MOTOR_ORACLE_CASE',None)
            if project:
                os.environ['PCB_MOTOR_PROJECT_PATH']=str(project);os.environ['PCB_MOTOR_VERSION_INDEX']=str(args.version)
            else:
                os.environ.pop('PCB_MOTOR_PROJECT_PATH',None);os.environ.pop('PCB_MOTOR_VERSION_INDEX',None)
            os.environ['CARGO_BUILD_JOBS']='1'
            run(['cargo','test','-p','pcbmotorgen','--bin','pcbmotorgen','export_magpylib_validation_fixture','--','--ignored','--nocapture'],root,str(folder/'export.log'))
            log=(folder/'export.log').read_text()
            binary=re.findall(r'Running unittests src/main.rs \(([^)]+)\)',log)
            if len(binary)!=1:raise ValueError('Cannot identify the executed Rust exporter test binary')
            executable=(root/binary[0]).resolve()
            run([sys.executable,str(root/'scripts/validate_magpylib.py'),'--fixture',str(fixture)],root,str(folder/'oracle.log'))
            data=json.loads(fixture.read_text());sim=data['sim'];drive=data['drive'];hints=data['geometry_hints']
            if sim.get('backplane') is not None:raise ValueError('Cannot qualify material physics using Magpylib')
            if data['force_subdivisions']!=n:raise ValueError('Exporter did not apply the requested quadrature level')
            networks={}
            for network in data['networks']:
                r=resistances(network,sim,drive,hints);shares,equivalent=unit_currents(network,r)
                _,dl=conductor_samples(network,shares,sim,hints,n)
                networks[network['net']]={'equivalent_resistance_ohm':equivalent,
                    'max_current_share_absolute_error':float(np.max(abs(shares-network['rust_current_share']))),
                    'max_edge_resistance_absolute_error_ohm':float(np.max(abs(r-[edge['r_ohm'] for edge in network['edges']]))),
                    'sample_count':len(dl),'vertical_sample_count':int(np.sum(abs(dl[:,2])>1e-15)),
                    'signed_total_dl_m':dl.sum(axis=0).tolist()}
            force=np.asarray(data['rust_force_x_n']);positions=np.asarray(data['force_positions_m'])
            if not np.isfinite(force).all() or force.shape!=positions.shape or force.ndim!=1 or len(force)<2:raise ValueError('Invalid source force curve')
            level={'fixture_sha256':sha(fixture),'exporter_binary_sha256':sha(executable),'networks':networks,
                   'driver_reference':data.get('driver_reference'),
                   'force_positions_m':positions.tolist(),'phase_a_force_x_n':force.tolist(),
                   'mean_absolute_phase_a_force_n':float(np.mean(abs(force))),'oracle_log_sha256':sha(folder/'oracle.log'),
                   'export_receipt_sha256':sha(folder/'export.log.command.json'),'oracle_receipt_sha256':sha(folder/'oracle.log.command.json')}
            if args.driver_reference:
                level['force_x_n']=level.pop('phase_a_force_x_n')
                level['mean_absolute_force_n']=level.pop('mean_absolute_phase_a_force_n')
            if previous is not None:
                np.testing.assert_array_equal(positions,previous['force_positions_m'])
                if level['exporter_binary_sha256']!=previous['exporter_binary_sha256']:raise ValueError('Exporter binary changed during study')
                change=float(np.linalg.norm(force-previous['force_x_n' if args.driver_reference else 'phase_a_force_x_n']))
                limit=max(1e-8,0.02*float(np.linalg.norm(force)))
                report['refinements'][str(n)]={'force_vector_absolute_change_n':change,'limit_n':limit,'passed':change<=limit}
            report['levels'][str(n)]=level;previous=level;save()
            print('mesh',n,'independent current/geometry/force checks pass',flush=True)
        if not report['refinements'][str(args.meshes[-1])]['passed']:report['failures'].append('Finest conductor refinement exceeds max(10nN, 2%)')
        for path,entry in sources.items():
            if sha(path)!=entry['sha256']:raise ValueError('Study implementation changed during validation')
        if project and sha(project)!=report['project_sha256']:raise ValueError('User project changed during study')
        report['status']='failed' if report['failures'] else 'passed-independent-winding-and-free-space-force-only';save()
        if report['failures']:raise RuntimeError('\n'.join(report['failures']))
    except BaseException as error:
        report['status']='failed';report['error']=str(error);save();raise


if __name__=='__main__':main()
