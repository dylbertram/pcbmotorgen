#!/usr/bin/env python3
"""Compare a saved project's single-layer periodic DC limit with real FEMM.

This deliberately does not claim finite five-magnet ends, cross-travel depth,
housing current closure, copper excitation, motion or inductance. Only one
magnetic layer and a nonmagnetic DC-transparent housing are supported.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from spectral_plate import solve
from check_plate2d import reference
import femm_backplane as femm


def inputs(path, version):
    raw=path.read_bytes();doc=json.loads(raw)
    if doc.get('format')!='pcbmotorgen-coil' or doc.get('format_version')!=1 or doc.get('document_type')!='motor':
        raise ValueError('Unsupported saved project')
    if isinstance(version,bool) or not isinstance(version,int) or not 0<=version<len(doc['versions']):raise ValueError('Invalid zero-based saved version')
    config=doc['versions'][version]['state']['config']
    if config['topology']!='linear':raise ValueError('Only alternating linear arrays are supported')
    stack=config['backplane']
    if not stack or len(stack['layers'])!=1:raise ValueError('Only a single magnetic layer is supported')
    layer=stack['layers'][0];material=layer['material']
    if material not in femm.LAYER:raise ValueError('Unknown magnetic material')
    mu=femm.LAYER[material][0] if layer.get('mu_r') is None else layer['mu_r']
    bsat=femm.BSAT.get(material) if layer.get('bsat_t') is None else layer['bsat_t']
    if mu<=1 or bsat is None or bsat<=0:raise ValueError('A saturable magnetic layer is required')
    housing=stack.get('housing')
    if housing and (housing['material'] not in femm.HOUSING or femm.HOUSING[housing['material']][0]!=1):
        raise ValueError('Magnetic/unsupported housing requires a multilayer solver')
    if housing and not (math.isfinite(housing['thickness_m']) and housing['thickness_m']>0 and
                        math.isfinite(housing['gap_m']) and housing['gap_m']>=0):
        raise ValueError('Invalid housing thickness or gap')
    geometry={'pole_pitch':config['electrical_pitch_mm']*0.5e-3,'pcb':config['pcb_thickness_mm']*1e-3,
              'gap':config['air_gap_mm']*1e-3,'width':config['magnet_width_mm']*1e-3,
              'height':config['magnet_height_mm']*1e-3,'br':config['magnet_remanence_t']}
    if not all(isinstance(v,(float,int)) and math.isfinite(v) and v>0 for v in [mu,bsat,layer['thickness_m'],*geometry.values()]):
        raise ValueError('Nonphysical material or geometry')
    if geometry['width']>=geometry['pole_pitch']:raise ValueError('Touching/overlapping magnets are unsupported')
    return config,stack,geometry,mu,bsat,hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--version',type=int,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--run-femm',action='store_true',help='run the actual Wine FEMM benchmark, otherwise require archived outputs')
    args=parser.parse_args()
    config,stack,geometry,mu,bsat,source_hash=inputs(args.project,args.version)
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    if (work/'summary.json').exists():parser.error('preserve the existing summary; use a new work directory')
    report={'scope':__doc__,'status':'running','source_sha256':source_hash,'version_index':args.version,
            'geometry':geometry,'stack':stack,'runs':{},'failures':[],
            'finite_magnet_count_not_modelled':config['magnet_count'],
            'finite_cross_width_mm_not_modelled':config['magnet_cross_width_mm'],
            'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    output=work/'summary.json';output.write_text(json.dumps(report,indent=2)+'\n')
    femm.G['remanence_t']=geometry['br'];femm.G['magnet_width_mm']=geometry['width']*1e3;femm.G['magnet_height_mm']=geometry['height']*1e3
    femm.TAU=geometry['pole_pitch']*1e3;femm.PERIOD=2*femm.TAU
    femm.T_PCB=geometry['pcb']*1e3;femm.Y_MAG0=(geometry['pcb']+geometry['gap'])*1e3;femm.Y_MAG1=femm.Y_MAG0+geometry['height']*1e3
    references={}
    for name,spec in [('bare',{'layers':[],'housing':None}),('stack',stack)]:
        label='project-periodic.'+name
        if args.run_femm:
            femm.run_femm(femm.build_case(label,spec,'magnets',nonlinear='knee'),str(work))
        path=work/(label+'.out');references[name]=reference(path)
    expected_ratio=references['stack']['mag_centre_pcb_top_By']/references['bare']['mag_centre_pcb_top_By']
    expected_pressure=references['stack']['Fy_stack']/(2*geometry['width'])
    for tag,cells,modes in [('base',32,9),('depth',64,9),('modes',64,17)]:
        result=solve(stack['layers'][0]['thickness_m'],mu,bsat,cells,modes,512,geometry)
        result.update(field_ratio_error=result['field_ratio']/expected_ratio-1,pressure_error=result['pressure_pa']/expected_pressure-1)
        report['runs'][tag]=result;print(tag,json.dumps(result),flush=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
    runs=report['runs']
    for first,second in [('base','depth'),('depth','modes')]:
        for key in ['field_ratio','pressure_pa']:
            if abs(runs[first][key]/runs[second][key]-1)>0.02:report['failures'].append(f'{first}->{second} {key} exceeds 2%')
    final=runs['modes']
    if abs(final['field_ratio_error'])>0.05 or abs(final['pressure_error'])>0.05:report['failures'].append('Independent FEMM agreement exceeds 5%')
    report.update(status='failed' if report['failures'] else 'comparison-only',
                  reference={'field_ratio':expected_ratio,'pressure_pa':expected_pressure},
                  femm_sha256={name:hashlib.sha256((work/('project-periodic.'+name+'.out')).read_bytes()).hexdigest() for name in references})
    output.write_text(json.dumps(report,indent=2)+'\n')
    if hashlib.sha256(args.project.read_bytes()).hexdigest()!=source_hash:raise ValueError('Source changed during the check')
    if report['failures']:raise SystemExit('\n'.join(report['failures']))


if __name__=='__main__':
    main()
