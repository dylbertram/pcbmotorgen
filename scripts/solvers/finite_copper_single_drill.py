#!/usr/bin/env python3
"""Exact declared copper: fuse by primitive kind, then cut all bores once.

Uses the identical finite trace/barrel/pad primitives and bore cylinders as
the original builder. Only Boolean grouping/order changes. Dimensions,
depths, connectivity, resistivity and geometry tolerances are unchanged.
The caller must still enforce nonempty connected copper and the independent
declared-primitive union-volume gate before accepting any preparation.
"""
import numpy as np

from audit_copper_union_volume import primitives
from finite_copper_eligibility import require_network_representable
from finite_copper_geometry import dimensions,fuse_all
from finite_copper_grouped import build_groups,kind


def build(fixture,shift):
    from netgen.occ import Cylinder,Pnt,Dir
    spec=dimensions(fixture);require_network_representable(fixture,spec)
    shift=np.asarray(shift,dtype=float)
    if shift.shape!=(3,) or not np.isfinite(shift).all():raise ValueError('Invalid rigid copper translation')
    pieces,groups,_=build_groups(fixture,shift)
    names=sorted({kind(g['label']) for g in groups})
    parts=[fuse_all([p for p,g in zip(pieces,groups) if kind(g['label'])==name]) for name in names]
    copper=fuse_all(parts)
    _,drills=primitives(fixture,shift)
    if drills:
        bore=fuse_all([Cylinder(Pnt(d['centre'][0],d['centre'][1],d['z'][0]),Dir(0,0,1),
            spec['via_inner_radius_m'],d['z'][1]-d['z'][0]) for d in drills])
        copper=copper-bore
    copper.mat('copper');copper.faces.name='copper_surface'
    return copper,dict(spec,trace_edges=sum(g['label'].startswith('trace:') for g in groups),
        distinct_via_positions=len(drills),solid_components=len(copper.solids),volume_m3=float(copper.mass),
        fuse_strategy='per-kind-single-drill',fuse_groups=names)
