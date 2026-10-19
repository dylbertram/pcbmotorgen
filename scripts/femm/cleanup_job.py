"""Stop orphan FEMM workers for one failed job, never every Wine process."""
import os
import signal
import sys
from pathlib import Path


def cleanup(prefix, directory, proc=Path("/proc"), kill=os.kill):
    directory = Path(directory).resolve()
    if directory == Path("/"):
        raise ValueError("Refusing root as a job directory")
    needle = ("z:" + str(directory).replace("/", "\\") + "\\").casefold()
    stopped = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().decode(errors="replace").split("\0")
            name = command[0].replace("\\", "/").rsplit("/", 1)[-1].casefold()
            if name not in {"fkn.exe", "triangle.exe"}:
                continue
            environment = (entry / "environ").read_bytes().split(b"\0")
            if os.fsencode("WINEPREFIX=" + str(prefix)) not in environment:
                continue
            if needle not in " ".join(command).casefold():
                continue
            kill(int(entry.name), signal.SIGKILL)
            stopped.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return stopped


if __name__ == "__main__":
    print("Stopped failed-job FEMM workers:", cleanup(sys.argv[1], sys.argv[2]))
