"""Independent SI-unit field comparison and directed-current continuity audit."""
import json
from collections import Counter, defaultdict
from pathlib import Path
import magpylib as magpy
import numpy as np

data = json.loads(Path("app/desktop/src-tauri/magpylib-fixture.json").read_text())
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
    positions = np.array([s["point"] for s in samples])
    dl = np.array([s["dl"] for s in samples])
    forces = []
    for offset in data["force_positions_m"]:
        # Moving the observations oppositely is equivalent to translating
        # every magnet by offset; current is fixed Phase A only at I_peak.
        observations = positions - np.array([offset, 0, 0])
        field = magnets.getB(observations)
        forces.append(-np.cross(dl, field).sum(axis=0)[0] * s["max_current_a"])
    rust_force = np.array(data["rust_force_x_n"])
    print("Corrected phase-A force maximum discrepancy [N]:", np.max(np.abs(forces-rust_force)))
    print("Corrected force relative norm discrepancy:", np.linalg.norm(forces-rust_force)/np.linalg.norm(rust_force))
    np.testing.assert_allclose(forces, rust_force, rtol=1e-8, atol=1e-10)

# Equal current in every stored directed segment must obey Kirchhoff's law
# at internal nodes. Vias join layers and carry no imposed direction here.
routing = data["routing"]
parent = {}
def node(point, layer):
    return (round(point["x"], 6), round(point["y"], 6), layer)
def root(n):
    parent.setdefault(n, n)
    if parent[n] != n:
        parent[n] = root(parent[n])
    return parent[n]
for via in routing["vias"]:
    a = root(node(via["position"], via["from_layer"]))
    b = root(node(via["position"], via["to_layer"]))
    parent[a] = b
by_net = defaultdict(Counter)
degree = defaultdict(Counter)
for seg in routing["segments"]:
    a, b = (root(node(seg[key], seg["layer"])) for key in ["start", "end"])
    by_net[seg["net"]][a] += 1
    by_net[seg["net"]][b] -= 1
    degree[seg["net"]][a] += 1
    degree[seg["net"]][b] += 1
for net, balance in by_net.items():
    invalid = [(n, v, degree[net][n]) for n, v in balance.items()
               if v and degree[net][n] > 1]
    print(net, "internal nodes violating equal directed-current continuity:", len(invalid),
          "examples:", invalid[:3])
