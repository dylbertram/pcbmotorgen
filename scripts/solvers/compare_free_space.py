#!/usr/bin/env python3
"""Compare accepted GetDP and Elmer cuboid jobs without retuning either one."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--getdp-work", required=True, type=Path)
    parser.add_argument("--elmer-work", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    summaries = {}
    data = {}
    for name, work in [("getdp", args.getdp_work), ("elmer", args.elmer_work)]:
        summaries[name] = json.loads((work / "summary.json").read_text())
        summary = summaries[name]
        assert summary.get("status") == "passed", f"{name} is not an accepted completed job"
        assert not summary["failures"], f"{name} has failed acceptance gates"
        assert summary["mesh_relative_change"] <= 0.02 and summary["domain_relative_change"] <= 0.02
        data[name] = np.loadtxt(work / "fine/field.txt")
        assert data[name].shape == (25, 6) and np.all(np.isfinite(data[name]))
    np.testing.assert_allclose(data["getdp"][:, :3], data["elmer"][:, :3], atol=1e-14, rtol=0)
    a, b = data["getdp"][:, 3:], data["elmer"][:, 3:]
    difference = np.linalg.norm(a-b)/np.linalg.norm(a)
    report = {"scope": "accepted linear free-space cuboid jobs, fine mesh",
              "relative_vector_norm_difference": difference, "maximum_component_difference_t": float(np.max(np.abs(a-b))),
              "versions": {name: s["versions"] for name, s in summaries.items()},
              "input_summary_sha256": {name: hashlib.sha256((work / "summary.json").read_bytes()).hexdigest()
                                        for name, work in [("getdp", args.getdp_work), ("elmer", args.elmer_work)]},
              "passed": bool(difference <= 0.05)}
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    if not report["passed"]:
        raise SystemExit(f"Cross-solver field disagreement {difference:.3%} exceeds 5%")
    print(f"PASS: GetDP/Elmer free-space vector field difference {difference:.3%}; not material or motion validation")


if __name__ == "__main__":
    main()
