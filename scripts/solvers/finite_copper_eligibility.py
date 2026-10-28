"""Reject raw geometry the legacy network-only copper builder cannot preserve.

This is an input-safety guard, not qualification or a geometry correction. New
exact imported preparation handles circular primitives and separate via spans.
"""


def require_network_representable(fixture, spec):
    routing = fixture.get('routing')
    if routing is None:
        return  # Historical network-only unit inputs have no raw-CAD claim.
    if any(routing.get(key) for key in ['curves', 'splines', 'io_traces', 'io_pads']):
        raise ValueError('Legacy finite copper cannot preserve raw curved/IO primitives; no chord substitution permitted')
    raw, graph = {}, {}
    for via in routing.get('vias', []):
        lo, hi = sorted([via['from_layer'], via['to_layer']])
        if type(lo) is not int or type(hi) is not int or not 0 <= lo < hi < len(spec['layers']):
            raise ValueError('Invalid raw physical via span')
        xy = (via['position']['x']*1e-3, via['position']['y']*1e-3)
        layers = set(range(lo, hi+1))
        intervals, pads = raw.setdefault(xy, ([], set()))
        intervals.append((min(spec['layers'][i]['centre_z_m']-spec['layers'][i]['thickness_m']/2 for i in layers),
                          max(spec['layers'][i]['centre_z_m']+spec['layers'][i]['thickness_m']/2 for i in layers)))
        pads.update(layers)
    for network in fixture['networks']:
        for edge in network['edges']:
            geometry = edge['geometry']
            if geometry['kind'] == 'trace' and 'circular_arc_m' in geometry:
                raise ValueError('Legacy finite copper cannot replace a circular primitive by graph chords')
            if geometry['kind'] == 'via':
                graph.setdefault(tuple(geometry['position_m']), set()).update(geometry['layers'])
    if set(raw) != set(graph):
        raise ValueError('Raw physical vias and electrical graph coverage differ')
    for xy,(intervals,pads) in raw.items():
        ordered = sorted(intervals);low,high = ordered[0]
        for a,b in ordered[1:]:
            if a > high:
                raise ValueError('Legacy finite copper would fill a gap between separate physical barrel spans')
            high = max(high,b)
        if pads != graph[xy]:
            raise ValueError('Legacy finite copper would truncate a physical barrel or omit unlanded annular pads')
