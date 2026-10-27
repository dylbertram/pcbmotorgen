"""SI field/force comparison and independent sparse nodal current solve.

Magpylib shares analytical cuboid physics with magba. Electrical graph extraction
and arc tessellation still come from Rust, not an independent topology oracle.
Resistances, branch currents and 3D trace/via dL are reconstructed independently.
"""
import json
import argparse
from pathlib import Path
import magpylib as magpy
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from solvers.winding_oracle import resistances,unit_currents,conductor_samples

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixture',type=Path,default=Path('app/desktop/src-tauri/magpylib-fixture.json'))
args=parser.parse_args()
data = json.loads(args.fixture.read_text())
s = data["sim"]
magnets = magpy.Collection(*[
    magpy.magnet.Cuboid(
        dimension=s["magnet_dims_m"],
        polarization=(0, 0, s["magnet_remanence_t"] * (-1)**k),
        position=(k*s["magnet_pitch_m"], s["board_width_m"]/2,
                  s["air_gap_m"] + s["magnet_dims_m"][2]/2))
    for k in range(s["magnet_count"])
])
points = np.array([(x, s["board_width_m"]/2, 0) for x in data["field_x_m"]])
reference = magnets.getB(points)
rust = np.array(data["rust_b_t"])
print("Magpylib", magpy.__version__)
print("Maximum B discrepancy [T]:", np.max(np.abs(reference-rust)))
print("Relative B norm discrepancy:", np.linalg.norm(reference-rust)/np.linalg.norm(reference))
np.testing.assert_allclose(reference, rust, rtol=1e-8, atol=1e-10)

if "phase_a_samples" not in data:
    raise ValueError("Fixture lacks signed-current force samples; re-export it")
if "phase_a_samples" in data:
    samples = data["phase_a_samples"]
    phases=[]
    for index,network in enumerate(data['networks']):
        resistance=resistances(network,s,data['drive'],data['geometry_hints'])
        shares,_=unit_currents(network,resistance)
        positions,dl=conductor_samples(network,shares,s,data['geometry_hints'],data['force_subdivisions'])
        actual=data['phase_samples'][index] if 'phase_samples' in data else samples if index==0 else None
        if actual is not None:
            np.testing.assert_allclose(positions,np.array([sample['point'] for sample in actual]),rtol=1e-12,atol=1e-14)
            np.testing.assert_allclose(dl,np.array([sample['dl'] for sample in actual]),rtol=1e-7,atol=1e-11)
        phases.append((positions,dl))
    excitation=np.asarray(data.get('excitation_currents_a',[[s['max_current_a']]+[0]*(len(phases)-1)]*len(data['force_positions_m'])))
    if excitation.shape!=(len(data['force_positions_m']),len(phases)) or not np.isfinite(excitation).all():raise ValueError('Invalid exported excitation')
    forces = []
    for offset,currents in zip(data["force_positions_m"],excitation):
        # Moving the observations oppositely is equivalent to translating
        # every magnet by offset; excitation commands are explicit inputs.
        force=0.
        for (positions,dl),current in zip(phases,currents):
            if current==0:continue
            observations = positions - np.array([offset, 0, 0])
            field = magnets.getB(observations)
            force-=np.cross(dl,field).sum(axis=0)[0]*current
        forces.append(force)
    rust_force = np.array(data["rust_force_x_n"])
    print("Corrected exported-excitation force maximum discrepancy [N]:", np.max(np.abs(forces-rust_force)))
    print("Corrected force relative norm discrepancy:", np.linalg.norm(forces-rust_force)/np.linalg.norm(rust_force))
    np.testing.assert_allclose(forces, rust_force, rtol=1e-8, atol=1e-10)
    if data.get('driver_reference'):
        independent_kf=float(np.mean(forces))/s['max_current_a']
        np.testing.assert_allclose(independent_kf,data['driver_reference']['kf_n_per_a'],rtol=1e-8,atol=1e-10)
        print('Independent force Kf with the exported excitation [N/A]:',independent_kf)
        print('Driver reference:',data['driver_reference'])
        print('Excitation is exported from the model, not an independent controller-waveform validation')

# Stored drawing directions are arbitrary. Solve branch currents instead of
# incorrectly assigning +1 to every edge and merely printing KCL violations.
if not data.get("networks"):
    raise ValueError("Fixture lacks resistor graphs; re-export it")
for net in data["networks"]:
    n = net["node_count"]
    a = np.array([e["a"] for e in net["edges"]])
    b = np.array([e["b"] for e in net["edges"]])
    resistance = resistances(net,s,data['drive'],data['geometry_hints'])
    np.testing.assert_allclose(resistance,np.array([e['r_ohm'] for e in net['edges']]),rtol=1e-10,atol=1e-12)
    assert np.all(np.isfinite(resistance)) and np.all(resistance > 0)
    conductance = 1 / resistance
    laplacian = coo_matrix((np.concatenate([conductance, conductance, -conductance, -conductance]),
                           (np.concatenate([a, b, a, b]), np.concatenate([a, b, b, a]))), shape=(n, n)).tocsr()
    potential = np.zeros(n)
    potential[net["terminal"]] = 1
    fixed = np.array(net["terminal"] + net["star"])
    unknown = np.setdiff1d(np.arange(n), fixed)
    potential[unknown] = spsolve(laplacian[unknown][:, unknown], -(laplacian @ potential)[unknown])
    raw_current = (potential[a] - potential[b]) / resistance
    inflow = np.bincount(a, weights=raw_current, minlength=n) - np.bincount(b, weights=raw_current, minlength=n)
    injected = inflow[net["terminal"]].sum()
    assert injected > 0 and np.all(np.isfinite(potential))
    shares = raw_current / injected
    np.testing.assert_allclose(inflow[unknown] / injected, 0, atol=1e-9)
    np.testing.assert_allclose(-inflow[net["star"]].sum(), injected, rtol=1e-9)
    equivalent = 1 / injected
    np.testing.assert_allclose(np.sum(shares**2 * resistance), equivalent, rtol=1e-9)
    np.testing.assert_allclose(shares, net["rust_current_share"], rtol=1e-7, atol=1e-8)
    np.testing.assert_allclose(equivalent, net["rust_resistance_ohm"], rtol=1e-8)
    print(net["net"], "independent nodal solve: KCL and power pass; R [ohm]", equivalent,
          "max branch discrepancy", np.max(np.abs(shares - net["rust_current_share"])))
