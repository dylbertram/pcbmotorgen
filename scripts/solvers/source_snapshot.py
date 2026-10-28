"""Content-addressed source copies for reproducible offline solver experiments."""
import hashlib
from pathlib import Path


def capture(work,paths):
    work=Path(work)
    result={}
    for path in [Path(__file__),*[Path(p) for p in paths]]:
        data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        destination=work/'source-snapshots'/digest/path.name
        destination.parent.mkdir(parents=True,exist_ok=True)
        try:
            with destination.open('xb') as output:output.write(data)
        except FileExistsError:
            if destination.read_bytes()!=data:raise ValueError('Changed content-addressed source snapshot')
        result[str(path.resolve())]={'sha256':digest,'snapshot':str(destination.relative_to(work))}
    return result
