#!/usr/bin/env python3
"""Refine the layered FEMM references, not the analytical approximation.

Runs nonlinear thin/thick ferrite, harmonic Al screening and travelling-wave
drag. Mesh and outer-domain changes are independent. Results are per 1 m depth,
not a validation of finite 3D housing currents. No constants are fitted.
"""
import argparse
import copy
import json
import math
from pathlib import Path

import femm_backplane as f


def refined(case, name, scale=1.0, far=None, air_mesh=1.0):
    result = copy.deepcopy(case)
    result["name"] = name
    for region in result["bands"] + result["rects"] + result["labels"]:
        if region.get("mesh", 0) > 0:
            region["mesh"] *= scale
        else:
            # Changing the outer boundary must not also change FEMM's automatic
            # air mesh. Weighted-stress force on a thin sheet is sensitive to it.
            region["mesh"] = air_mesh
    if far is not None:
        result["bands"][0]["y0"] = result["bands"][0]["y1"] - far
        result["bands"][-1]["y1"] = result["bands"][-1]["y0"] + far
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--case", choices=["thin", "thick", "pwm", "drag"], nargs="+",
                        help="run selected cases only; default runs all four")
    parser.add_argument("--mesh-scale", type=float, default=1.0,
                        help="initial mesh multiplier, then halved and quartered")
    parser.add_argument("--far-air-mesh", type=float, default=1.0,
                        help="far-air mesh in mm, refined independently from the material and gap mesh")
    args = parser.parse_args()
    if not 0 < args.mesh_scale <= 1:
        parser.error("--mesh-scale must be greater than zero and at most one")
    if not math.isfinite(args.far_air_mesh) or args.far_air_mesh <= 0:
        parser.error("--far-air-mesh must be positive and finite")
    args.work.mkdir(parents=True, exist_ok=True)
    f.set_pcb(0.8)
    ferrite = lambda t: {"layers": [f.layer("flex_ferrite", t)], "housing": None}
    aluminum = {"layers": [], "housing": f.housing("aluminum6061", 1.0, 0.3)}
    cases = [
        ("thin", f.build_case("thin", ferrite(0.2), "magnets", nonlinear=True),
         {"Fy_stack": 0.01, "pcb_top_By1": 1e-5}),
        ("thick", f.build_case("thick", ferrite(5.0), "magnets", nonlinear=True),
         {"Fy_stack": 0.01, "pcb_top_By1": 1e-5}),
        ("pwm", f.build_case("pwm", aluminum, f.sheet_rects([f.sheet_ys(2)[1]]), freq=100e3),
         {"AJ_sources_re": 1e-12, "AJ_sources_im": 1e-12}),
        ("drag", f.build_case("drag", aluminum, f.sheet_rects([f.sheet_ys(2)[1]], travelling=True), freq=20 / 0.012),
         {"Fx_stack": 1e-8, "loss_stack": 1e-8}),
    ]
    report = {"scope": "FEMM 4.2 planar, 1 m depth; fixed material data", "status": "running", "initial_mesh_scale": args.mesh_scale, "far_air_mesh_mm": args.far_air_mesh, "cases": {}}
    (args.work / "convergence.json").write_text(json.dumps(report, indent=2)+"\n")
    failures = []
    for name, case, floors in cases:
        if args.case and name not in args.case:
            continue
        runs = {}
        for tag, scale, far, air_scale in [("base", 1, None, 1), ("half", 0.5, None, 1), ("quarter", 0.25, None, 1),
                                            ("airhalf", 0.5, None, 0.5), ("domain60", 0.5, 60, 1)]:
            runs[tag] = f.run_femm(refined(case, f"convergence.{name}.{tag}", scale*args.mesh_scale, far,
                                         args.far_air_mesh*air_scale), str(args.work))
            report["cases"][name] = {"results": runs}
            (args.work / "convergence.json").write_text(json.dumps(report, indent=2)+"\n")
        changes = {}
        for first, second in [("base", "half"), ("half", "quarter"), ("half", "airhalf"), ("half", "domain60")]:
            changes[f"{first}->{second}"] = {}
            for key, floor in floors.items():
                a, b = runs[first][key], runs[second][key]
                if not math.isfinite(a) or not math.isfinite(b):
                    failures.append(f"{name} {key}: nonfinite result")
                delta = abs(a-b) / max(abs(b), floor)
                changes[f"{first}->{second}"][key] = delta
                if delta > 0.02:
                    failures.append(f"{name} {first}->{second} {key}: {delta:.2%} > 2%")
        if name == "drag":
            for tag, values in runs.items():
                ratio = values["loss_stack"] / (values["Fx_stack"] * 20)
                if abs(ratio - 1) > 0.02:
                    failures.append(f"drag {tag}: Joule/drag power ratio {ratio}")
        report["cases"][name] = {"results": runs, "relative_changes": changes}
        print(name, json.dumps(changes), flush=True)
    report["failures"] = failures
    report["status"] = "failed" if failures else "passed"
    (args.work / "convergence.json").write_text(json.dumps(report, indent=2) + "\n")
    if failures:
        raise SystemExit("\n".join(failures))
    print("PASS: mesh, domain and drag-power gates. This does not validate 3D motion.")


if __name__ == "__main__":
    main()
