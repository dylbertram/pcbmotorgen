"""Explicit rigid translation from exported winding to finite-source coordinates.

The winding exporter places PCB top at z=0 and the first magnet at
x=mover_position, y=board_width/2. Finite-source models place PCB bottom at
z=0 and the whole PM array at array_centre_mm. This translation moves the
observations, not the finite material geometry. Using it at another mover
position does NOT move magnets relative to a fixed backplane: that requires
a new bias solve with the backplane held fixed.
"""
import numpy as np


def translation(sim, model, mover_position_m):
    keys=['magnet_count','magnet_pitch_m','magnet_remanence_t','pcb_thickness_m','board_width_m']
    if any(k not in sim for k in keys):raise ValueError('Missing exported winding dimensions')
    count=sim['magnet_count']
    if type(count) is not int or count<1 or count!=len(model['magnets']):raise ValueError('Different magnet counts')
    values=[sim[k] for k in keys[1:]]+[mover_position_m]
    if not np.isfinite(values).all() or min(values[:-1])<=0:raise ValueError('Invalid winding dimensions/pose')
    if not np.isclose(sim['pcb_thickness_m'],model['pcb_thickness_m'],rtol=1e-12,atol=1e-15):
        raise ValueError('Winding and finite bias use different PCB thicknesses')
    centre=np.asarray(model['array_centre_mm'],dtype=float)*1e-3
    if centre.shape!=(2,) or not np.isfinite(centre).all():raise ValueError('Invalid finite array centre')
    dimensions=np.asarray(sim['magnet_dims_m'],dtype=float)
    if dimensions.shape!=(3,) or not np.isfinite(dimensions).all() or np.min(dimensions)<=0:
        raise ValueError('Invalid exported magnet dimensions')
    pitch=sim['magnet_pitch_m']
    for i,magnet in enumerate(model['magnets']):
        origin=np.asarray(magnet['origin_m'],dtype=float);size=np.asarray(magnet['size_m'],dtype=float)
        expected_xy=centre+np.array([(i-(count-1)/2)*pitch,0.])-dimensions[:2]/2
        expected_z=sim['pcb_thickness_m']+sim['air_gap_m']
        polarization=[0.,0.,sim['magnet_remanence_t']*(-1)**i]
        if not np.allclose(size,dimensions,rtol=1e-12,atol=1e-15) or not np.allclose(origin,np.r_[expected_xy,expected_z],rtol=1e-12,atol=1e-15):
            raise ValueError('Finite magnet geometry differs from exported winding source')
        if not np.allclose(magnet['polarization_t'],polarization,rtol=1e-12,atol=1e-15):
            raise ValueError('Finite magnet polarity differs from exported source')
    return np.array([centre[0]-(count-1)*pitch/2-mover_position_m,
                     centre[1]-sim['board_width_m']/2,sim['pcb_thickness_m']])


def translate_samples(points, signed_dl, sim, model, mover_position_m):
    points=np.asarray(points,dtype=float);signed_dl=np.asarray(signed_dl,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or signed_dl.shape!=points.shape or not np.isfinite([points,signed_dl]).all():
        raise ValueError('Invalid signed 3D conductor samples')
    # A translation changes neither current direction nor physical layer spacing.
    return points+translation(sim,model,mover_position_m),signed_dl.copy()
