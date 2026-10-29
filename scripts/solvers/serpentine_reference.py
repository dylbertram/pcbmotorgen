"""Independent Magpylib force quadrature for the legacy serpentine geometry.

This reads geometry only, never the obsolete fixture's force/ripple values or
Rust output. Explicit cos currents with phase zero pi fix the mover-force sign.
It checks Lorentz integration under that declared excitation, not controller
qualification, imported copper, material response or hardware performance.
"""
import argparse
import hashlib
import json
import platform
from pathlib import Path

import magpylib
import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT / 'crates/pcbmotorgen-simulation/scripts/fixtures/test_vectors.json'
REFERENCE = ROOT / 'crates/pcbmotorgen-simulation/scripts/fixtures/serpentine-force-reference-v2.json'
PHYSICAL = dict(magnet_dims_m=[.01,.01,.004], magnet_count=10, magnet_pitch_m=.012,
                magnet_remanence_t=1.35, active_area_length_m=.195, board_width_m=.02,
                air_gap_m=.0005, max_current_a=1., spacing_ratio=1., phases=3)


def calculate(coils, physical, subdivisions, count=20):
    """Signed mover force; SI positions, actual segment order and midpoint rule."""
    p = physical
    width, _, height = p['magnet_dims_m']
    pitch = p['magnet_pitch_m']
    start = width / 2
    end = p['active_area_length_m'] - (p['magnet_count']-1)*pitch - width/2
    positions = np.linspace(start,end,count)
    centres=[np.array([k*pitch,p['board_width_m']/2,p['air_gap_m']+height/2])
             for k in range(p['magnet_count'])]
    offsets = np.arange(len(coils))*np.pi*p['spacing_ratio']/p['phases']
    currents = p['max_current_a']*np.cos(np.pi*positions[:,None]/pitch + np.pi-offsets)
    samples=[]
    for coil in coils:
        points=[];vectors=[]
        for segment in coil['segments']:
            if not segment['is_active']:continue
            a=np.r_[np.asarray(segment['start_mm'])*.001,0.]
            b=np.r_[np.asarray(segment['end_mm'])*.001,0.]
            dl=(b-a)/subdivisions
            points.extend(a+(np.arange(subdivisions)+.5)[:,None]*dl)
            vectors.extend(np.tile(dl,(subdivisions,1)))
        samples.append((np.asarray(points),np.asarray(vectors)))
    forces=[]
    for x,phase_currents in zip(positions,currents):
        force=np.zeros(3)
        for (points,dl),current in zip(samples,phase_currents):
            # All cuboids are axis aligned. Use Magpylib's direct functional
            # interface, without an unnecessary SciPy identity-rotation path.
            field=np.zeros_like(points)
            for k,centre in enumerate(centres):
                field+=magpylib.func.cuboid_field('B',points-np.array([x,0,0])-centre,
                    p['magnet_dims_m'],(0,0,p['magnet_remanence_t']*(-1)**k))
            force-=np.cross(dl,field).sum(axis=0)*current
        forces.append(force)
    forces=np.asarray(forces)
    if not np.isfinite(forces).all():raise ValueError('Nonfinite reference force')
    fx=forces[:,0]
    return dict(subdivisions=subdivisions,positions_m=positions.tolist(),phase_currents_a=currents.tolist(),
                force_xyz_n=forces.tolist(),mean_thrust_n=float(fx.mean()),
                ripple_pct=float((fx.max()-fx.min())/abs(fx.mean())*100))


def generate():
    raw=GEOMETRY.read_bytes()
    coils=json.loads(raw)['coils_serpentine']
    levels=[calculate(coils,PHYSICAL,n) for n in [20,40,80]]
    refinements=[]
    for a,b in zip(levels,levels[1:]):
        delta=float(np.linalg.norm(np.asarray(a['force_xyz_n'])-b['force_xyz_n']))
        gate=max(1e-10,.02*float(np.linalg.norm(b['force_xyz_n'])))
        if delta>gate:raise ValueError('Independent conductor refinement failed 2% gate')
        refinements.append(dict(coarse=a['subdivisions'],fine=b['subdivisions'],absolute_change_n=delta,limit_n=gate))
    return dict(schema='independent-serpentine-force-v2',
                scope=__doc__,physical_inputs=PHYSICAL,phase_zero_rad=float(np.pi),
                geometry_sha256=hashlib.sha256(raw).hexdigest(),
                generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                runtime=dict(python=platform.python_version(),magpylib=magpylib.__version__,numpy=np.__version__,scipy=scipy.__version__),
                reference_tolerances=dict(force_relative=1e-8,force_absolute_n=1e-10,ripple_absolute_pct=1e-6),
                refinements=refinements,levels=levels)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REFERENCE)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    result=generate()
    if args.check:
        recorded=json.loads(args.output.read_text())
        if recorded!=result:raise SystemExit('Recorded reference differs; preserve evidence and investigate before replacing')
        print('Independent geometry/current/force/reference hashes and refinements match')
    else:
        with args.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
        print(args.output)
