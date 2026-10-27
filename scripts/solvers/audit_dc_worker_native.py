#!/usr/bin/env python3
"""Inventory a pinned macOS worker's loaded native images and license evidence.

Read-only technical evidence, not redistribution clearance or isolated-install
acceptance. Imports and the existing AMG smoke load runtime components, never
CAD, a winding mesh, a field or a force solve. Outputs are exclusive.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys

from check_dc_worker import HERE, preparation_smoke, problems, required_packages


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def loaded_images():
    if sys.platform!='darwin':raise ValueError('Loaded-image inventory requires macOS dyld')
    library=ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    count=library._dyld_image_count;count.restype=ctypes.c_uint32
    name=library._dyld_get_image_name;name.argtypes=[ctypes.c_uint32];name.restype=ctypes.c_char_p
    return sorted({name(index).decode() for index in range(count()) if name(index)})


def license_files(distribution):
    result=[]
    for item in distribution.files or []:
        path=Path(distribution.locate_file(item))
        if any(token in path.name.lower() for token in ['license','licence','copying','notice','copyright']) and path.is_file():
            result.append(dict(path=str(path.resolve()),sha256=digest(path),bytes=path.stat().st_size))
    return result


def linkage(path):
    path=Path(path)
    if not path.is_file():
        return dict(status='not-a-standalone-file',note='May be a system shared-cache image; not independently inspected')
    result=subprocess.run(['/usr/bin/otool','-L',str(path)],capture_output=True,text=True,timeout=15)
    if result.returncode:
        return dict(status='inspection-failed',returncode=result.returncode,stderr=result.stderr)
    dependencies=[line.strip().split(' (',1)[0] for line in result.stdout.splitlines()[1:] if line.strip()]
    return dict(status='inspected',path=str(path.resolve()),sha256=digest(path),dependencies=dependencies,
        relocatable_dependencies=[value for value in dependencies if value.startswith('@')],
        scope='Mach-O declared linkage; relocatable paths are recorded, not assumed resolved or licensed')


def inventory(preparation=False):
    required=required_packages(HERE/'requirements-dc-worker.txt',preparation)
    found=problems(required)
    if found:raise ValueError('Pinned environment rejected: '+'; '.join(found))
    import recalculate_dc_request, finite_current_coupling, desktop_dc_job, dc_applicability  # noqa: F401
    import sample_dc_winding_field, desktop_dc_winding_field  # noqa: F401
    # Worker modules import the solver lazily inside their entry points. Load
    # its actual extensions explicitly without meshing or solving anything.
    import ngsolve  # noqa: F401
    from netgen import occ  # noqa: F401
    smoke=None
    if preparation:
        import dc_preparation, prepare_dc_request, desktop_dc_preparation  # noqa: F401
        smoke=preparation_smoke()
    imported_modules={}
    for name in ['ngsolve','netgen','numpy','scipy','pyamg','recalculate_dc_request','desktop_dc_job',
                 'dc_applicability','sample_dc_winding_field','desktop_dc_winding_field',
                 'dc_preparation','prepare_dc_request','desktop_dc_preparation']:
        module=sys.modules.get(name);filename=getattr(module,'__file__',None)
        if filename and Path(filename).is_file():
            imported_modules[name]=dict(path=str(Path(filename).resolve()),sha256=digest(filename))
    images=loaded_images()
    owners={}
    packages=[]
    for package,version in required.items():
        distribution=metadata.distribution(package)
        for item in distribution.files or []:
            path=Path(distribution.locate_file(item))
            if path.suffix in ['.so','.dylib']:owners.setdefault(str(path.resolve()),[]).append(package)
        packages.append(dict(name=package,version=version,metadata_license=distribution.metadata.get('License'),
            license_expression=distribution.metadata.get('License-Expression'),
            classifiers=[value for value in distribution.metadata.get_all('Classifier',[]) if value.startswith('License ::')],
            license_files=license_files(distribution)))
    native=[]
    for image in images:
        path=Path(image);system=image.startswith(('/System/','/usr/lib/'))
        native.append(dict(loaded_path=image,owners=owners.get(str(path.resolve()),[]),system_image=system,
            inspection=dict(status='system-image-not-inspected') if system else linkage(path)))
    return dict(schema='dc-worker-native-inventory-v1',status='inventory-completed-clearance-open',
        observed_at_utc=datetime.now(timezone.utc).isoformat(),python=sys.executable,python_prefix=sys.prefix,
        preparation=preparation,preparation_smoke=smoke,imported_modules=imported_modules,packages=packages,loaded_images=native,
        implementation_sha256=digest(Path(__file__)),
        requirements_hashes={str(HERE/name):digest(HERE/name) for name in ['requirements-dc-worker.txt','requirements-dc-preparation.txt']},
        unresolved=['Not an isolated macOS installation test',
            'Only components loaded by these imports/smoke are observed; optional native paths may load more',
            'Relocatable dependency resolution and all transitively redistributed components need separate review',
            'Package metadata and license-file hashes do not establish applicable linkage/source/notice obligations',
            'Homebrew/interpreter/system components without pinned-distribution ownership need separate provenance review',
            'Redistribution clearance is not granted; no delivery artifacts created'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preparation',action='store_true');args=parser.parse_args()
    if args.output.exists():parser.error('Preserve earlier native inventory evidence')
    report=inventory(args.preparation)
    with args.output.open('x') as stream:stream.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],packages=len(report['packages']),loaded_images=len(report['loaded_images']),
        output=str(args.output),sha256=digest(args.output)),indent=2))


if __name__=='__main__':main()
