#!/usr/bin/env python3
"""Receipt-producing child of the desktop's owned POSIX process group.

Do not detach nested solvers. The desktop owns cancellation and a whole-job
timeout; this supervisor also bounds and records its direct request worker.
Executable and archive paths are host configuration, not request fields.
"""
import argparse
from pathlib import Path
import sys

from check_dc_worker import pins, problems
from check_free_space import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    # Refuse an unpinned/incompatible installation before any job evidence or solve.
    found = problems(pins(Path(__file__).with_name('requirements-dc-worker.txt')))
    if found:
        raise SystemExit('DC worker environment differs from the pinned qualified installation: '+'; '.join(found))
    run([sys.executable, str(Path(__file__).with_name('recalculate_dc_request.py').resolve()),
         '--request', str(args.request.resolve()), '--archive-root', str(args.archive_root.resolve()),
         '--work', str(args.job.resolve()/'result')], args.job.resolve(), 'desktop-worker.log',
        new_process_group=False)


if __name__ == '__main__':
    main()
