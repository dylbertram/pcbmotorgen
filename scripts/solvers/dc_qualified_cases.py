"""Registry of individually qualified linear DC cases for live recalculation.

A case is admitted only through its own passing whole-matrix audit: every
recorded evidence hash is re-verified before use. The registry stores which
audited cache/bias/bare/pose works a fresh live solve reuses; it never stores
or serves a force. A design matching no registered case needs qualification.
"""
import json
from pathlib import Path

from dc_request_contract import physical_model

REGISTRY = 'dc-qualified-linear-cases-v1.json'
AUDIT_STATUSES = {'passed-recorded-actual-geometry-dc-force-matrix-only',
                  'passed-declared-case-actual-geometry-dc-force-matrix-only'}
POSES = {'nominal': 0., 'plus100um': .0001, 'minus100um': -.0001}


def resolve(root, value):
    path = Path(value)
    return path if path.is_absolute() else Path(root)/path


def read_registry(root):
    path = Path(root)/REGISTRY
    if not path.exists():
        return dict(schema='dc-qualified-linear-cases-v1', cases=[])
    registry = json.loads(path.read_text())
    if registry.get('schema') != 'dc-qualified-linear-cases-v1' or not isinstance(registry.get('cases'), list):
        raise ValueError('Unrecognized qualified-case registry')
    return registry


def verify_case(root, entry, evidence):
    """Return the verified physical case or raise; never trusts registry text alone."""
    audit_path = resolve(root, entry['audit'])
    if evidence.digest(audit_path) != entry['audit_sha256']:
        raise ValueError('Registered audit changed: '+entry['case_id'])
    audit = evidence.report(audit_path)
    if (audit.get('status') not in AUDIT_STATUSES or audit.get('magnetic_jobs') != 37 or
            audit.get('saved_current_states') != 185 or audit.get('control_pairs') != 44):
        raise ValueError('Registered case lacks a complete passing force-matrix audit: '+entry['case_id'])
    for path, digest in audit['evidence_hashes'].items():
        if evidence.digest(path) != digest:
            raise ValueError('Qualified evidence changed: '+entry['case_id'])
    bound = set(audit['evidence_hashes'])
    fixture = str(resolve(root, entry['fixture']).resolve())
    source_path = str((resolve(root, entry['source'])/'summary.json').resolve())
    if fixture not in bound or source_path not in bound:
        raise ValueError('Registered fixture/source is not audited evidence: '+entry['case_id'])
    live = {}
    for pose, inputs in entry['live'].items():
        if pose not in POSES:
            raise ValueError('Registered live pose is outside the qualified sample')
        paths = [resolve(root, inputs['cache'])/'summary.json', resolve(root, inputs['bias'])/'summary.json', resolve(root, inputs['bare'])]
        if inputs.get('pose_reference'):
            paths.append(resolve(root, inputs['pose_reference'])/'summary.json')
        if any(str(path.resolve()) not in bound for path in paths):
            raise ValueError('Registered live input was not verified by the case audit: '+entry['case_id'])
        live[POSES[pose]] = {key: str(resolve(root, value)) for key, value in inputs.items() if value}
    if set(live) != set(POSES.values()):
        raise ValueError('Every qualified PM pose needs its audited live inputs')
    source = evidence.report(Path(source_path))
    current = evidence.report(Path(source['source_work'])/'summary.json')
    if audit['status']=='passed-declared-case-actual-geometry-dc-force-matrix-only':
        from audit_linear_dc_source_force_controls import verify_source_force_audit
        control_path=audit.get('source_refinement_force_audit')
        if not control_path or str(resolve(root,control_path).resolve()) not in bound:
            raise ValueError('New case lacks audited downstream source-refinement force controls')
        verify_source_force_audit(evidence,resolve(root,control_path),audit['actual_model'],evidence.digest(Path(source['source_work'])/'summary.json'))
    return dict(case_id=entry['case_id'], label=entry['label'], audit_sha256=entry['audit_sha256'],
                fixture=json.loads(Path(fixture).read_text()), model=audit['actual_model'], current_geometry=current['geometry'],
                source_hash=evidence.digest(Path(source_path)), live=live)


def declaration(case):
    """The explicit audited placement/return a user may acknowledge for that case."""
    keys = ['return_path_m', 'return_width_m', 'return_thickness_m', 'drive_path_m']
    return dict(material_model=physical_model(case['model']), return_geometry={key: case['current_geometry'][key] for key in keys})
