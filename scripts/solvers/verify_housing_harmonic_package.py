#!/usr/bin/env python3
"""Read back the delivered ZIP and source archive without executing the app."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile


def digest(stream):
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(chunk)
    return value.hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return digest(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve existing verification evidence")
    work = args.delivery.resolve()
    manifest = json.loads((work / "verification.json").read_text())
    expected = {
        manifest["zip"]: manifest["zip_sha256"],
        "source.tar.gz": manifest["source_archive_sha256"],
        "source.diff": manifest["source_diff_sha256"],
    }
    for name, value in expected.items():
        if file_digest(work / name) != value:
            raise ValueError("Delivery hash mismatch: " + name)
    for line in (work / "SHA256SUMS").read_text().splitlines():
        value, name = line.split("  ", 1)
        if file_digest(work / name) != value:
            raise ValueError("SHA256SUMS mismatch: " + name)
    app_files = manifest["app_files_sha256"]
    with zipfile.ZipFile(work / manifest["zip"]) as archive:
        names = [entry.filename for entry in archive.infolist() if not entry.is_dir()
                 and entry.filename.startswith("pcbmotorgen.app/")]
        if len(names) != len(set(names)) or set(names) != set(app_files):
            raise ValueError("ZIP app inventory differs from manifest")
        for name, value in app_files.items():
            with archive.open(name) as stream:
                if digest(stream) != value:
                    raise ValueError("ZIP content mismatch: " + name)
            if file_digest(work / name) != value:
                raise ValueError("App content mismatch: " + name)
    sources = manifest["source_files_sha256"]
    with tarfile.open(work / "source.tar.gz", "r:gz") as archive:
        entries = archive.getmembers()
        names = [entry.name for entry in entries]
        if len(names) != len(set(names)) or set(names) != set(sources):
            raise ValueError("Source archive inventory differs from manifest")
        for entry in entries:
            if not entry.isfile():
                raise ValueError("Unexpected non-file source archive member")
            with archive.extractfile(entry) as stream:
                if digest(stream) != sources[entry.name]:
                    raise ValueError("Source archive content mismatch: " + entry.name)
    args.output.write_text(json.dumps({
        "status": "passed-complete-zip-app-and-source-readback",
        "delivery": str(work), "zip_sha256": manifest["zip_sha256"],
        "verification_sha256": file_digest(work / "verification.json"),
        "app_files_checked": len(app_files), "source_files_checked": len(sources),
        "scope": "Archive integrity only; not native rendering or physics qualification",
    }, indent=2) + "\n")
    print("Verified complete ZIP/app/source inventories and every file hash")


if __name__ == "__main__":
    main()
