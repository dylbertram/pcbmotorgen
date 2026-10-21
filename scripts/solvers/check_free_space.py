#!/usr/bin/env python3
"""Run a headless GetDP/Gmsh PM check with archived inputs and convergence.

This is an installation and free-space formulation gate, not a qualified
backplane or eddy-current backend. Requires the validation Python environment.
"""
import argparse
import hashlib
import json
import os
import math
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

import magpylib as magpy
import numpy as np
from read_vtu import sample_vector
from job_status import process_identity

HERE = Path(__file__).resolve().parent


def run(command, work, log):
    start = time.monotonic()
    timeout = float(os.environ.get('PCB_MOTOR_SOLVER_TIMEOUT','600'))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('PCB_MOTOR_SOLVER_TIMEOUT must be positive and finite')
    receipt = {"command": command, "status": "running", "timeout_seconds": timeout,
               "cleanup_scope": "owned-posix-process-group" if os.name=='posix' else "single-process-descendants-unqualified"}
    receipt_path = work / (log+".command.json")
    if (work / log).exists():
        raise FileExistsError('Preserve solver evidence; use a new log name')
    # Exclusive receipt creation reserves this job name even for simultaneous
    # retries. A duplicate must not truncate an active/completed job's evidence.
    with receipt_path.open('x') as reserved:
        reserved.write(json.dumps(receipt, indent=2)+"\n")
    with (work / log).open('x') as output:
        try:
            child_environment=os.environ.copy()
            child_environment['PCB_MOTOR_COMMAND_RECEIPT']=str(receipt_path.resolve())
            process = subprocess.Popen(command, cwd=work, text=True, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=os.name=='posix',env=child_environment)
        except BaseException as error:
            receipt.update(status='spawn-failed',error=str(error),seconds=time.monotonic()-start)
            receipt_path.write_text(json.dumps(receipt, indent=2)+"\n")
            raise
        # A mocked or malformed process handle must never be coerced into an
        # OS process-group id. In particular MagicMock's integer value is 1.
        pid=process.pid
        if type(pid) is not int or pid<=1:
            receipt.update(status='invalid-process-handle',seconds=time.monotonic()-start)
            receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
            raise ValueError('Solver process handle does not have a safe owned PID')
        receipt['pid']=pid
        receipt['process_identity']=process_identity(pid)
        receipt['supervisor_pid']=os.getpid()
        receipt['supervisor_identity']=process_identity(os.getpid())
        def terminate_owned_job():
            if os.name=='posix':
                try:os.killpg(pid,signal.SIGKILL)
                except ProcessLookupError:pass
            else:process.kill()
            process.wait()
        manage_term=os.name=='posix' and threading.current_thread() is threading.main_thread()
        previous_term=None
        if manage_term:
            def cancelled(signum,frame):raise SystemExit(128+signum)
            previous_term=signal.signal(signal.SIGTERM,cancelled)
        try:
            receipt_path.write_text(json.dumps(receipt, indent=2)+"\n")
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            terminate_owned_job()
            output.write(f"\nFAILED: solver timeout after {timeout:g} seconds\n")
            receipt.update(status="timeout", seconds=time.monotonic()-start)
            receipt_path.write_text(json.dumps(receipt, indent=2)+"\n")
            raise RuntimeError(f"Solver timed out; see {work / log}") from error
        except BaseException:
            terminate_owned_job()
            receipt.update(status='interrupted', seconds=time.monotonic()-start)
            receipt_path.write_text(json.dumps(receipt, indent=2)+"\n")
            raise
        finally:
            if manage_term:signal.signal(signal.SIGTERM,previous_term)
        if code:terminate_owned_job()
    text = (work / log).read_text()
    failed = code or any(marker in text for marker in ["Error   :", "DIVERGED_", "ERROR::", "NOT CONVERGED"])
    if failed and not code:terminate_owned_job()
    receipt.update(status="failed" if failed else "completed", exit_code=code, seconds=time.monotonic()-start)
    receipt_path.write_text(json.dumps(receipt, indent=2)+"\n")
    if failed:
        raise RuntimeError(f"Failed solver command, exit {code}: {command}; see {work / log}")
    return time.monotonic() - start


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gmsh", required=True, type=Path)
    parser.add_argument("--getdp", type=Path)
    parser.add_argument("--elmer", type=Path)
    parser.add_argument("--elmergrid", type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--coarse-mesh", type=float, default=0.0004)
    parser.add_argument("--fine-mesh", type=float, default=0.0003)
    args = parser.parse_args()
    if bool(args.getdp) == bool(args.elmer) or (args.elmer and not args.elmergrid):
        parser.error("choose --getdp, or --elmer with --elmergrid")
    if not 0 < args.fine_mesh < args.coarse_mesh:
        parser.error("mesh sizes must be positive, with fine smaller than coarse")
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    report = {"scope": "linear free-space cuboid only", "status": "running", "magpylib": magpy.__version__, "runs": {}}
    (work / "summary.json").write_text(json.dumps(report, indent=2)+"\n")
    report["versions"] = {"gmsh": subprocess.check_output([str(args.gmsh.resolve()), "-version"], stderr=subprocess.STDOUT, text=True).strip()}
    if args.getdp:
        report["versions"]["getdp"] = subprocess.check_output([str(args.getdp.resolve()), "-version"], stderr=subprocess.STDOUT, text=True).strip()
    else:
        report["versions"]["elmer_sha256"] = hashlib.sha256(args.elmer.read_bytes()).hexdigest()
    magnet = magpy.magnet.Cuboid(dimension=(0.005, 0.005, 0.003), polarization=(0, 0, 1.34), position=(0, 0, 0.002))
    fields = {}
    failures = []
    for tag, size, radius in [("coarse", args.coarse_mesh, 0.03), ("fine", args.fine_mesh, 0.03), ("domain", args.fine_mesh, 0.045)]:
        job = work / tag
        job.mkdir(exist_ok=True)
        for name in ["cuboid.geo", "cuboid.pro", "cuboid.sif"]:
            shutil.copyfile(HERE / name, job / name)
        mesh_time = run([str(args.gmsh.resolve()), "cuboid.geo", "-3", "-format", "msh2", "-o", "cuboid.msh",
                         "-setnumber", "h", str(size), "-setnumber", "radius", str(radius), "-v", "4"], job, "mesh.log")
        if args.getdp:
            solve_time = run([str(args.getdp.resolve()), "cuboid.pro", "-msh", "cuboid.msh", "-solve", "SolvePM", "-v", "4",
                              "-ksp_type", "cg", "-pc_type", "gamg", "-ksp_rtol", "1e-10", "-ksp_max_it", "2000",
                              "-ksp_converged_reason", "-ksp_error_if_not_converged"], job, "solve.log")
            assert "CONVERGED_" in (job / "solve.log").read_text(), "No linear convergence evidence"
            table = np.loadtxt(job / "field.txt")
        else:
            run([str(args.elmergrid.resolve()), "14", "2", "cuboid.msh", "-out", "mesh", "-autoclean"], job, "convert.log")
            solve_time = run([str(args.elmer.resolve()), "cuboid.sif"], job, "solve.log")
            files = list(job.glob("**/fields*.vtu"))
            assert len(files) == 1, files
            observations = np.column_stack([np.linspace(-0.003, 0.003, 25), np.zeros((25, 2))])
            table = np.column_stack([observations, sample_vector(files[0], observations)])
            np.savetxt(job / "field.txt", table)
        assert table.shape == (25, 6), table.shape
        reference = magnet.getB(table[:, :3])
        fields[tag] = table[:, 3:]
        error = np.linalg.norm(fields[tag] - reference) / np.linalg.norm(reference)
        if not np.all(np.isfinite(table)) or error > 0.05:
            failures.append(f"{tag}: relative field norm error {error:.3%} > 5%")
        report["runs"][tag] = {"mesh_m": size, "air_radius_m": radius, "relative_field_norm_error": error,
                                "mesh_seconds": mesh_time, "solve_seconds": solve_time,
                                "sha256": {name: hashlib.sha256((job / name).read_bytes()).hexdigest()
                                           for name in ["cuboid.geo", "cuboid.pro", "cuboid.sif", "cuboid.msh"]}}
        print(tag, error, "mesh/solve seconds", mesh_time, solve_time, flush=True)
        (work / "summary.json").write_text(json.dumps(report, indent=2)+"\n")
    for tag, other in [("mesh", "coarse"), ("domain", "domain")]:
        change = np.linalg.norm(fields[other] - fields["fine"]) / np.linalg.norm(fields["fine"])
        report[tag + "_relative_change"] = change
        if change > 0.02:
            failures.append(f"{tag} refinement: field norm change {change:.3%} > 2%")
    report["failures"] = failures
    report["status"] = "failed" if failures else "passed"
    (work / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    if failures:
        raise SystemExit("\n".join(failures))
    print("PASS: free-space fields and refinement gates. Nonlinear materials and motion remain unvalidated.")


if __name__ == "__main__":
    main()
