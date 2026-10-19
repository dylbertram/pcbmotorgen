#!/usr/bin/env python3
"""Independent Elmer nonlinear plate comparison against archived FEMM jobs.

Uses one half-period of the alternating row with the corresponding natural
A_z side condition. The same two-slope B-H input is supplied to both solvers;
there is no permeability fit. This is still planar, not finite-depth motion.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from check_free_space import run
from read_vtu import values

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "femm"))
from femm_backplane import bh_points

MU0 = 4e-7 * math.pi


def sif(mu, nonlinear, relaxation=1.0):
    bh = '  H-B Curve = Variable "dummy"\n    Real\n      INCLUDE HB\n    End' if nonlinear else ''
    return f'''Include "mesh/mesh.names"
Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
End
Simulation
  Coordinate System = Cartesian 2D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Max Output Level = 12
End
Constants
  Permeability of Vacuum = {MU0:.17g}
End
Body 1
  Target Bodies(1) = 1
  Equation = 1
  Material = 1
End
Body 2
  Target Bodies(1) = 2
  Equation = 1
  Material = 2
End
Body 3
  Target Bodies(1) = 3
  Equation = 1
  Material = 3
End
Material 1
  Relative Permeability = 1
  Electric Conductivity = 0
End
Material 2
  Relative Permeability = 1
  Electric Conductivity = 0
  Magnetization 2 = {1.34/MU0:.17g}
End
Material 3
  Relative Permeability = {mu:.17g}
  Electric Conductivity = 0
{bh}
End
Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = VectorPotential
  Variable = A
  Variable DOFs = 1
  Procedure = "MagnetoDynamics2D" "MagnetoDynamics2D"
  Linear System Solver = Direct
  Linear System Direct Method = UMFPACK
  Linear System Convergence Tolerance = 1e-12
  Linear System Abort Not Converged = True
  Nonlinear System Max Iterations = 100
  Nonlinear System Convergence Tolerance = 1e-9
  Nonlinear System Relaxation Factor = {relaxation:.17g}
  Newton-Raphson Iteration = True
End
Solver 2
  Exec Solver = After All
  Equation = ResultOutput
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = fields
  Vtu Format = True
  Binary Output = False
End
Boundary Condition 1
  Target Boundaries(1) = $ far
  A = Real 0
End
'''


@lru_cache(maxsize=2)
def _potential_mesh(path, modified_ns, size):
    """Cache geometry, with size and mtime preventing reuse of replaced output."""
    if Path(path).suffix == '.pos':
        text = Path(path).read_text()
        entries = re.findall(r'ST\(([^)]+)\)\{([^}]+)\};',text)
        if not entries:
            raise ValueError('Expected scalar triangles in ASCII Gmsh potential output')
        data = np.array([np.fromstring(coords+','+scalar,sep=',') for coords,scalar in entries])
        if data.shape[1] != 12 or not np.isfinite(data).all():
            raise ValueError('Expected three coordinates and one scalar per triangle vertex')
        points = data[:,:9].reshape(-1,3)[:,:2]
        potential = data[:,9:].ravel()
        triangles = np.arange(len(points)).reshape(-1,3)
    else:
        piece = ET.parse(path).getroot().find("./UnstructuredGrid/Piece")
        points = values(piece.find("./Points/DataArray")).reshape(-1, 3)[:, :2]
        fields = {a.get("Name", "").casefold(): a for a in piece.findall("./PointData/DataArray")}
        potential = values(fields["a"])
        cells = {a.get("Name"): values(a) for a in piece.findall("./Cells/DataArray")}
        offsets = np.r_[0, cells["offsets"]]
        triangles = np.array([cells["connectivity"][offsets[i]:offsets[i+1]] for i, kind in enumerate(cells["types"]) if kind == 5])
    assert triangles.ndim == 2 and triangles.shape[1] == 3
    vertices = points[triangles]
    matrix = vertices[:, 1:] - vertices[:, :1]
    gradients = np.linalg.solve(matrix, (potential[triangles[:, 1:]] - potential[triangles[:, :1]])[..., None])[..., 0]
    flux = np.column_stack([gradients[:, 1], -gradients[:, 0]])
    lo, hi = vertices.min(axis=1), vertices.max(axis=1)
    centres = vertices.mean(axis=1)
    radii = np.linalg.norm(vertices-centres[:, None, :], axis=2).max(axis=1)
    # Separate element sizes so distant coarse-air triangles do not turn every
    # fine-gap query into a scan of the entire mesh. Balls enclose each triangle.
    buckets = []
    levels = np.floor(np.log2(radii)).astype(int)
    for level in np.unique(levels):
        indices = np.flatnonzero(levels == level)
        buckets.append((indices, cKDTree(centres[indices]), radii[indices].max()+1e-12))
    return vertices, matrix, flux, lo, hi, buckets


def raw_field(path, observations):
    """Curl of linear A_z, without projecting across material interfaces."""
    path = Path(path)
    stat = path.stat()
    vertices, matrix, flux, lo, hi, buckets = _potential_mesh(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    observations = np.asarray(observations)
    candidates_by_point = [[] for _ in observations]
    for indices, tree, radius in buckets:
        for found, neighbours in zip(candidates_by_point, tree.query_ball_point(observations, radius)):
            found.extend(indices[neighbours])
    result = []
    for point, candidates in zip(observations, candidates_by_point):
        candidates = np.asarray(candidates, dtype=int)
        candidates = candidates[np.all(point >= lo[candidates]-1e-12, axis=1) & np.all(point <= hi[candidates]+1e-12, axis=1)]
        assert candidates.size, f"No element at {point}"
        v = vertices[candidates]
        bary = np.linalg.solve(matrix[candidates].transpose(0, 2, 1), (point-v[:, 0])[..., None])[..., 0]
        inside = np.all(bary >= -1e-8, axis=1) & (bary.sum(axis=1) <= 1+1e-8)
        assert inside.any(), f"Point not in candidate elements: {point}"
        result.append(flux[candidates[inside]].mean(axis=0))
    result = np.array(result)
    assert np.all(np.isfinite(result))
    return result


def measure(path, thickness):
    # Integrate piecewise-constant element stress exactly along each air line.
    # Uniform samples can alias an unstructured mesh, especially at fine sizes.
    pressures = []
    for distance in [0.00005, 0.0001, 0.0002]:
        pressures.append((line_stress(path, distance)-line_stress(path, -thickness-distance))/0.005)
    return {"pcb_centre_by_t": float(raw_field(path, [[0, 0.0008]])[0, 1]), "pressure_pa": pressures[1],
            "stress_path_pressures_pa": pressures}


def line_stress(path, y, xmin=-0.003, xmax=0.003):
    y = np.nextafter(float(y), np.inf)
    path = Path(path)
    stat = path.stat()
    vertices, _, flux, lo, hi, _ = _potential_mesh(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    selected = np.flatnonzero((lo[:, 1] < y) & (hi[:, 1] > y))
    triangles = vertices[selected]
    intersections = []
    for a, b in [(0,1), (1,2), (2,0)]:
        start, end = triangles[:, a], triangles[:, b]
        dy = end[:, 1]-start[:, 1]
        t = np.divide(y-start[:, 1], dy, out=np.full_like(dy, np.nan), where=dy != 0)
        x = start[:, 0]+t*(end[:, 0]-start[:, 0])
        intersections.append(np.where((t >= 0) & (t <= 1), x, np.nan))
    intersections = np.array(intersections)
    left, right = np.nanmin(intersections, axis=0), np.nanmax(intersections, axis=0)
    lengths = np.maximum(0, np.minimum(right, xmax)-np.maximum(left, xmin))
    assert abs(lengths.sum()/(xmax-xmin)-1) < 1e-8, "Stress path is not fully covered by triangles"
    b = flux[selected]
    return float(lengths @ ((b[:,1]**2-b[:,0]**2)/(2*MU0)))


def reference(path):
    return {key: float(value) for key, value in (line.split() for line in path.read_text().splitlines())}


def validate_regions(mesh, thickness):
    nodes = {int(v[0]): np.array([float(x) for x in v[2:4]])
             for v in (line.split() for line in (mesh / "mesh.nodes").read_text().splitlines())}
    areas = {}
    for line in (mesh / "mesh.elements").read_text().splitlines():
        v = [int(x) for x in line.split()]
        assert v[2] == 303, "Only linear triangles are supported"
        a, b, c = [nodes[i] for i in v[3:]]
        area = abs((b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1]))/2
        areas[v[1]] = areas.get(v[1], 0.0) + area
    assert set(areas) == {1, 2, 3}, f"Missing material regions: {areas}"
    assert abs(areas[2]/(0.005*0.003)-1) < 1e-6, areas
    assert abs(areas[3]/(0.006*thickness)-1) < 1e-6, areas
    return areas


def validate_gmsh_regions(path, thickness):
    lines = path.read_text().splitlines()
    start = lines.index("$Nodes")
    count = int(lines[start+1])
    nodes = {int(v[0]): np.array([float(x) for x in v[1:3]])
             for v in (line.split() for line in lines[start+2:start+2+count])}
    start = lines.index("$Elements")
    count = int(lines[start+1])
    areas = {}
    for line in lines[start+2:start+2+count]:
        v = [int(x) for x in line.split()]
        if v[1] != 2:
            continue
        a,b,c = [nodes[i] for i in v[3+v[2]:]]
        area = abs((b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1]))/2
        areas[v[3]] = areas.get(v[3],0)+area
    assert set(areas) == {1,2,3}, areas
    assert abs(areas[2]/(0.005*0.003)-1) < 1e-6, areas
    assert abs(areas[3]/(0.006*thickness)-1) < 1e-6, areas
    return areas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["gmsh", "femm-work", "work"]:
        parser.add_argument("--"+name, required=True, type=Path)
    for name in ["elmer", "elmergrid", "getdp"]:
        parser.add_argument("--"+name, type=Path)
    parser.add_argument("--quick", action="store_true", help="base mesh only; does not pass a refinement gate")
    parser.add_argument("--case", choices=["flex_0.2", "flex_5", "mnzn_2"], nargs="+")
    parser.add_argument("--initial-mesh", type=float, default=0.00002)
    parser.add_argument("--relaxation",type=float,default=1.0)
    args = parser.parse_args()
    if bool(args.getdp) == bool(args.elmer) or (args.elmer and not args.elmergrid):
        parser.error("choose --getdp, or --elmer with --elmergrid")
    if not 0 < args.initial_mesh <= 0.0001:
        parser.error("--initial-mesh must be positive and at most 0.1 mm")
    if not 0 < args.relaxation <= 1:
        parser.error("--relaxation must be positive and at most one")
    args.work = args.work.resolve()
    args.work.mkdir(parents=True, exist_ok=True)
    report = {"scope": "planar nonlinear, one half-period, two-slope BH", "status": "running", "backend": "getdp" if args.getdp else "elmer", "cases": {}, "refined": not args.quick}
    (args.work / "summary.json").write_text(json.dumps(report, indent=2)+"\n")
    failures = []
    base_ref = reference(args.femm_work / "v2.none.mag.out")
    for label, thickness, mu, bsat in [("flex_0.2", 0.0002, 130, 0.25), ("flex_5", 0.005, 130, 0.25), ("mnzn_2", 0.002, 2500, 0.45)]:
        if args.case and label not in args.case:
            continue
        runs = {}
        levels = [("base", args.initial_mesh, 0.04)] if args.quick else [("base", args.initial_mesh, 0.04), ("fine", args.initial_mesh/2, 0.04), ("domain", args.initial_mesh/2, 0.06)]
        for tag, h, far in levels:
            results = []
            for biased in [False, True]:
                job = args.work / f"{label}.{tag}.{'plate' if biased else 'bare'}"
                job.mkdir(exist_ok=True)
                shutil.copyfile(HERE / "plate2d.geo", job / "plate2d.geo")
                (job / "case.sif").write_text(sif(mu if biased else 1, biased,args.relaxation))
                (job / "HB").write_text("\n".join(f"{b:.17g} {h_:.17g}" for b, h_ in bh_points(mu, bsat, knee=True))+"\n")
                (job / "request.json").write_text(json.dumps({"backend": report["backend"], "mu_initial": mu,
                    "saturation_polarization_t": bsat, "biased_plate": biased, "thickness_m": thickness,
                    "mesh_m": h, "air_extent_m": far, "solver_relaxation":args.relaxation}, indent=2)+"\n")
                run([str(args.gmsh.resolve()), "plate2d.geo", "-2", "-format", "msh2", "-o", "plate.msh", "-setnumber", "thickness", str(thickness),
                     "-setnumber", "h", str(h), "-setnumber", "far", str(far), "-v", "4"], job, "mesh.log")
                areas = validate_gmsh_regions(job / "plate.msh", thickness)
                if args.getdp:
                    shutil.copyfile(HERE / "plate2d.pro", job / "plate2d.pro")
                    elapsed = run([str(args.getdp.resolve()), "plate2d.pro", "-msh", "plate.msh", "-solve", "SolvePlate", "-v", "4",
                                   "-setnumber", "Mu", str(mu), "-setnumber", "Bsat", str(bsat), "-setnumber", "Biased", str(int(biased)),
                                   "-setnumber", "Relaxation",str(args.relaxation),
                                   "-setnumber", "Thickness", str(thickness), "-ksp_type", "gmres", "-pc_type", "lu",
                                   "-pc_factor_mat_solver_type", "mumps", "-ksp_rtol", "1e-12", "-ksp_atol", "1e-14",
                                   "-ksp_error_if_not_converged", "-ksp_converged_reason", "-mat_mumps_icntl_10", "5"], job, "solve.log")
                    residual = np.loadtxt(job / "nonlinear.txt").reshape(-1, 2)[-1]
                    assert "CONVERGED_" in (job / "solve.log").read_text(), "No linear convergence evidence"
                    assert np.all(np.isfinite(residual))
                    assert (0 <= residual[0] <= 1e-9) if biased else residual[0] == -1, residual
                    result = measure(job / 'potential.pos', thickness)
                    inputs = ["plate2d.geo", "plate2d.pro", "plate.msh"]
                else:
                    run([str(args.elmergrid.resolve()), "14", "2", "plate.msh", "-out", "mesh", "-autoclean"], job, "convert.log")
                    validate_regions(job / "mesh", thickness)
                    elapsed = run([str(args.elmer.resolve()), "case.sif"], job, "solve.log")
                    log = (job / "solve.log").read_text()
                    if "System has converged to tolerances" not in log:
                        raise RuntimeError(f"No nonlinear convergence evidence: {job}")
                    output = list(job.glob("**/fields*.vtu"))
                    assert len(output) == 1, output
                    result = measure(output[0], thickness)
                    inputs = ["plate2d.geo", "case.sif", "HB", "plate.msh"]
                inputs.append("request.json")
                result.update(solve_seconds=elapsed, material_areas_m2=areas, sha256={name: hashlib.sha256((job/name).read_bytes()).hexdigest() for name in inputs})
                results.append(result)
            bare, plate = results
            assert abs(bare["pcb_centre_by_t"]) > 1e-6, "No PM excitation in the bare-field reference"
            ratio = plate["pcb_centre_by_t"] / bare["pcb_centre_by_t"]
            pressure = plate["pressure_pa"] - bare["pressure_pa"]
            ref = reference(args.femm_work / f"v2.{label}.knee.out")
            expected_ratio = ref["mag_centre_pcb_top_By"] / base_ref["mag_centre_pcb_top_By"]
            expected_pressure = ref["Fy_stack"] / 0.01
            if max(abs(p) for p in bare["stress_path_pressures_pa"]) > 0.02*abs(expected_pressure):
                failures.append(f"{label} {tag}: no-plate stress floor exceeds 2% of reference force")
            rerr, perr = ratio/expected_ratio-1, pressure/expected_pressure-1
            runs[tag] = {"bare": bare, "plate": plate, "field_ratio": ratio, "pressure_pa": pressure,
                         "field_ratio_error": rerr, "pressure_error": perr, "reference": {"field_ratio": expected_ratio, "pressure_pa": expected_pressure}}
            if abs(rerr) > 0.05 or abs(perr) > 0.05:
                failures.append(f"{label} {tag}: FEMM agreement field {rerr:.2%}, pressure {perr:.2%} exceeds 5%")
            path_change = max(abs(p-plate["pressure_pa"]) for p in plate["stress_path_pressures_pa"]) / abs(pressure)
            if path_change > 0.02 and (args.quick or tag != "base"):
                failures.append(f"{label} {tag}: Maxwell-stress path sensitivity {path_change:.2%} > 2%")
            print(label, tag, "field ratio", ratio, "pressure Pa", pressure, "FEMM errors", rerr, perr, flush=True)
            report["cases"][label] = runs
            (args.work / "summary.json").write_text(json.dumps(report, indent=2)+"\n")
        if not args.quick:
            for first, second in [("base", "fine"), ("fine", "domain")]:
                for key in ["field_ratio", "pressure_pa"]:
                    change = abs(runs[first][key]/runs[second][key]-1)
                    if change > 0.02:
                        failures.append(f"{label} {first}->{second} {key}: {change:.2%} > 2%")
        report["cases"][label] = runs
        report["failures"] = failures
        (args.work / "summary.json").write_text(json.dumps(report, indent=2)+"\n")
    report["status"] = "failed" if failures else ("comparison-only" if args.quick else "passed")
    (args.work / "summary.json").write_text(json.dumps(report, indent=2)+"\n")
    if failures:
        raise SystemExit("\n".join(failures))
    print("PASS" if not args.quick else "Comparison passed; refinement not run")


if __name__ == "__main__":
    main()
