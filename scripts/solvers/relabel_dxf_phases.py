"""Swap B/C names in a DXF without reserializing or moving any geometry.

Back up the exact input bytes and record hashes before replacing the source.
Only complete phase names or underscore-delimited phase suffixes on DXF
string groups are changed. Numeric groups and line endings are untouched.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def sha(data):
    return hashlib.sha256(data).hexdigest()


def swap(data):
    lines = data.splitlines(keepends=True)
    if len(lines) % 2:
        raise ValueError('DXF must contain complete group/value pairs')
    changed = Counter()
    for i in range(0, len(lines), 2):
        code = int(lines[i].strip())
        # Layer definitions, references, and optional literal phase text.
        if code not in (1, 2, 3, 8):
            continue
        value = lines[i + 1]
        match = re.fullmatch(rb'((?:[^\r\n]*_)?)([BC])(\r?\n)?', value)
        if match:
            prefix, phase, ending = match.groups()
            replacement = b'C' if phase == b'B' else b'B'
            changed[(prefix + phase).decode('ascii')] += 1
            lines[i + 1] = prefix + replacement + (ending or b'')
    return b''.join(lines), dict(changed)


def relabel(path, backup):
    original = path.read_bytes()
    corrected, changes = swap(original)
    if not changes or swap(corrected)[0] != original:
        raise ValueError('Phase swap must be nonempty and exactly reversible')
    backup.mkdir(parents=True, exist_ok=True)
    destination = backup / path.name
    with destination.open('xb') as stream:
        stream.write(original)
    receipt = dict(source=str(path.resolve()), backup=str(destination.resolve()),
                   original_sha256=sha(original), corrected_sha256=sha(corrected),
                   replacements=changes, geometry_and_other_bytes_unchanged=True)
    with (backup / (path.name + '.json')).open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    if path.read_bytes() != original:
        raise ValueError('Source changed during relabeling')
    path.write_bytes(corrected)
    assert path.read_bytes() == corrected
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('files', type=Path, nargs='+')
    args = parser.parse_args()
    for path in args.files:
        print(json.dumps(relabel(path, args.backup), indent=2))
