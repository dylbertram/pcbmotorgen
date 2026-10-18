#!/usr/bin/env python3
"""FEMM 4.2 check of the t707 backplane model (stdlib only).

    python3 -I scripts/femm/femm_backplane.py [--work DIR] [--dxf FILE]

Builds 2-D planar FEMM cases (one electrical period, periodic in x, A = 0 far
above and below), runs them through run_femm.sh, runs the Rust model through
the backplane_dump example, and prints Markdown tables for RESULTS.md.

Coordinates in the FEMM model: x along travel, y up, mm. y = 0 is the PCB
bottom face (top of the backplane stack), the PCB spans 0..1.6, the magnets
sit 0.5 mm above it.

The model check uses the model's own assumptions:
  * inductance: equal sinusoidal current sheets (wavenumber pi/tau), one per
    copper layer, spread evenly from the PCB bottom to the PCB top. Each sheet
    is solved alone and factor = sum(A.J with stack) / sum(A.J without), which
    is the model's equal-weight average. A second run drives all sheets at
    once, so it includes the coupling between sheets that the model leaves out;
  * attraction / field: the alternating magnet row, linear materials.
The benchmark slice cuts the benchmark winding (DXF) at the middle of the board and
reports the line-to-line inductance factor of that copper layout.

Saturation and eddy currents (tickets 04n2, q9nw), on the user's version 2
geometry (0.8 mm PCB) unless noted:
  * nonlinear magnetostatics with the magnet row and a smooth B-H curve,
    B = mu0 H + Bsat tanh(mu0 (mu_i - 1) H / Bsat), so the same initial mu and
    saturation as the model's two-slope curve but a soft knee;
  * the coil sheets solved with the incremental permeability of that biased
    state (FEMM's mi_setprevious), for two alignments of coil and magnets;
  * time-harmonic coil sheets at 100 kHz (inductance and added resistance);
  * a travelling current sheet J0 e^(-jkx) at f = v/(2 tau), which is the magnet
    fundamental seen from the stator at speed v: time-averaged x and y force
    on the stack and housing against -Im R and Re R.
"""
import argparse
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MU0 = 4e-7 * math.pi

# Benchmark geometry (closed_infinity_pattern.pmmotor): electrical pitch 12 mm,
# so pole pitch tau = 6 mm. The magnets are 5 mm deep; the model gets 1 m so its
# attraction is the 2-D value that the planar FEMM slice computes.
G = dict(pole_pitch_mm=6.0, magnet_width_mm=5.0, magnet_cross_width_mm=1000.0,
         magnet_height_mm=3.0, magnet_count=5, remanence_t=1.34,
         air_gap_mm=0.5, pcb_thickness_mm=1.6)
TAU = G["pole_pitch_mm"]
PERIOD = 2 * TAU
T_PCB = G["pcb_thickness_mm"]
Y_MAG0 = T_PCB + G["air_gap_mm"]
Y_MAG1 = Y_MAG0 + G["magnet_height_mm"]
FAR = 40.0  # distance to the A = 0 lines; exp(-pi*40/6) ~ 1e-9
PWM_HZ = 100e3

# Same mu_r, conductivity [MS/m] and Bsat [T] as
# crates/pcbmotorgen-simulation/src/backplane/mod.rs.
LAYER = {
    "fr4": (1.0, 0.0),
    "silicon_steel": (4000.0, 2.0),
    "mn_zn_ferrite": (2500.0, 0.2e-6),
    "ni_zn_ferrite": (500.0, 0.0),
    "flex_ferrite": (130.0, 0.0),
}
HOUSING = {
    "aluminum6061": (1.0, 25.0),
    "steel1018": (800.0, 5.8),
}
BSAT = {"silicon_steel": 1.8, "mn_zn_ferrite": 0.45, "ni_zn_ferrite": 0.35,
        "flex_ferrite": 0.25, "steel1018": 1.6}


def layer(material, t_mm, mu_r=None):
    lay = {"material": material, "thickness_m": t_mm * 1e-3}
    if mu_r is not None:
        # A linear stand-in at a model permeability: no saturation.
        lay.update(mu_r=mu_r, bsat_t=3.0)
    return lay


def housing(material, t_mm, gap_mm):
    return {"material": material, "thickness_m": t_mm * 1e-3, "gap_m": gap_mm * 1e-3}


CASES = [
    ("none", "No backplane", {"layers": [], "housing": None}),
    ("fr4_1.6", "FR4 1.6 mm", {"layers": [layer("fr4", 1.6)], "housing": None}),
    ("mnzn_2", "MnZn 2 mm", {"layers": [layer("mn_zn_ferrite", 2.0)], "housing": None}),
    ("mnzn_5", "MnZn 5 mm", {"layers": [layer("mn_zn_ferrite", 5.0)], "housing": None}),
    ("sisteel_0.35", "Si steel 0.35 mm", {"layers": [layer("silicon_steel", 0.35)], "housing": None}),
    ("flex_0.3", "Flex ferrite 0.3 mm", {"layers": [layer("flex_ferrite", 0.3)], "housing": None}),
    ("nizn_2", "NiZn 2 mm", {"layers": [layer("ni_zn_ferrite", 2.0)], "housing": None}),
    ("fr4_1+mnzn_2", "FR4 1 mm + MnZn 2 mm", {"layers": [layer("fr4", 1.0), layer("mn_zn_ferrite", 2.0)], "housing": None}),
    ("mnzn_2+al", "MnZn 2 mm + Al 3 mm @1 mm", {"layers": [layer("mn_zn_ferrite", 2.0)], "housing": housing("aluminum6061", 3.0, 1.0)}),
    ("mnzn_2+steel", "MnZn 2 mm + steel 3 mm @1 mm", {"layers": [layer("mn_zn_ferrite", 2.0)], "housing": housing("steel1018", 3.0, 1.0)}),
    ("al_only", "Al 3 mm @1 mm (no layers)", {"layers": [], "housing": housing("aluminum6061", 3.0, 1.0)}),
    ("steel_only", "Steel 3 mm @1 mm (no layers)", {"layers": [], "housing": housing("steel1018", 3.0, 1.0)}),
    ("mnzn_1+fr4_0.5+mnzn_1", "MnZn 1 mm + FR4 0.5 mm + MnZn 1 mm",
     {"layers": [layer("mn_zn_ferrite", 1.0), layer("fr4", 0.5), layer("mn_zn_ferrite", 1.0)], "housing": None}),
    ("flex_0.3+sisteel_0.35", "Flex ferrite 0.3 mm + Si steel 0.35 mm",
     {"layers": [layer("flex_ferrite", 0.3), layer("silicon_steel", 0.35)], "housing": None}),
    ("flex_0.3+fr4_0.2+flex_0.3", "Flex 0.3 mm + FR4 0.2 mm + flex 0.3 mm",
     {"layers": [layer("flex_ferrite", 0.3), layer("fr4", 0.2), layer("flex_ferrite", 0.3)], "housing": None}),
]
# Cases with conductive material that also get a 100 kHz run.
AC_CASES = {"none", "sisteel_0.35", "mnzn_2+al", "mnzn_2+steel", "al_only", "steel_only"}


# --------------------------------------------------------------------------
# FEMM case description
# --------------------------------------------------------------------------

def lua(v):
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k} = {lua(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(lua(x) for x in v) + "}"
    if isinstance(v, str):
        return json.dumps(v)
    return repr(float(v))


def mesh_for(t):
    return min(t / 4.0, 0.25)


def bh_points(mu_i, bsat, knee=False):
    """B-H curve with initial mu_i and saturation polarization bsat: smooth
    (tanh), or the model's two-slope curve when `knee`."""
    if not knee:
        hs = [0.0] + [10 ** (e / 8) for e in range(57)]  # 1 A/m .. 1e7 A/m
        return [(MU0 * h + bsat * math.tanh(MU0 * (mu_i - 1) * h / bsat), h) for h in hs]
    # Dense points on both sides of the knee keep FEMM's spline on the lines.
    h_knee = bsat / (MU0 * (mu_i - 1))
    hs = [h_knee * f for f in (0, 0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 0.99, 1.0)]
    hs += [h_knee * (1 + 10 ** (e / 8)) for e in range(-24, math.ceil(8 * math.log10(1e7 / h_knee)) + 1)]
    return [(MU0 * h + min(MU0 * (mu_i - 1) * h, bsat), h) for h in hs]


def stack_bands(stack, freq, nonlinear=False):
    """Bands below y = 0 (bottom to top) and the materials they use."""
    mats, bands = {}, []
    y = 0.0
    for lay in stack["layers"]:
        t = lay["thickness_m"] * 1e3
        mu, sig = LAYER[lay["material"]]
        name = lay["material"]
        if "mu_r" in lay:
            mu, name = lay["mu_r"], f"{name}_mu{lay['mu_r']:.4g}"
        mats[name] = dict(name=name, mu=mu, sigma=sig if freq else 0.0)
        if nonlinear and name in BSAT:
            mats[name]["bh"] = bh_points(mu, BSAT[name], nonlinear == "knee")
        bands.append(dict(y0=y - t, y1=y, mat=name if mu > 1 else "air",
                          mesh=mesh_for(t), group=2 if mu > 1 else 0))
        y -= t
    h = stack["housing"]
    if h:
        gap, t = h["gap_m"] * 1e3, h["thickness_m"] * 1e3
        mu, sig = HOUSING[h["material"]]
        mats[h["material"]] = dict(name=h["material"], mu=mu, sigma=sig if freq else 0.0)
        if nonlinear and h["material"] in BSAT:
            mats[h["material"]]["bh"] = bh_points(mu, BSAT[h["material"]], nonlinear == "knee")
        bands.append(dict(y0=y - gap, y1=y, mat="air", mesh=mesh_for(gap), group=0))
        y -= gap
        if freq and sig > 0:
            # Resolve the skin depth near the face toward the source.
            delta = 1e3 * math.sqrt(2 / (2 * math.pi * freq * mu * MU0 * sig * 1e6))
            skin = min(5 * delta, t / 2)
            bands.append(dict(y0=y - skin, y1=y, mat=h["material"], mesh=max(delta / 3, 0.002), group=2))
            bands.append(dict(y0=y - t, y1=y - skin, mat=h["material"], mesh=mesh_for(t), group=2))
        else:
            bands.append(dict(y0=y - t, y1=y, mat=h["material"], mesh=mesh_for(t), group=2))
        y -= t
    if freq:
        # Silicon steel at 100 kHz: refine the top of the sheet the same way.
        for b in bands:
            m = mats.get(b["mat"])
            if m and m["sigma"] > 0.1 and b["group"] == 2 and b["mat"] not in HOUSING:
                delta = 1e3 * math.sqrt(2 / (2 * math.pi * freq * m["mu"] * MU0 * m["sigma"] * 1e6))
                b["mesh"] = max(delta / 3, 0.002)
    bands.reverse()
    bands.insert(0, dict(y0=y - FAR, y1=y, mat="air", mesh=0, group=0))
    bands.sort(key=lambda b: b["y0"])
    return bands, list(mats.values())


SHEET_T = 0.02  # current sheet thickness [mm]
PEAK_N = 48  # samples of |B| along the stack top


def sheet_ys(layers):
    """Sheet centres for `layers` copper layers, evenly from the PCB bottom face
    to the top face (the model's d_i = i*T/(N-1)), kept inside the PCB."""
    return [SHEET_T / 2 + i * (T_PCB - SHEET_T) / (layers - 1) for i in range(layers)]


def sheet_rects(ys, n=48, t=SHEET_T, j0=1.0, phase=0.0, travelling=False, live=None):
    """Equal sinusoidal current sheets at heights `ys`, wavenumber pi/tau, as
    n strips each: J0 cos(kx - phase), or the phasor J0 e^(-jkx) when
    `travelling`. Only the sheets listed in `live` carry current (all by
    default); the others keep the geometry."""
    mats, rects = [], []
    w = PERIOD / n
    for s, y in enumerate(ys):
        on = j0 if live is None or s in live else 0.0
        for i in range(n):
            xc = -PERIOD / 2 + (i + 0.5) * w
            name = f"src{s}_{i}"
            th = math.pi * xc / TAU - phase
            mats.append(dict(name=name, mu=1.0, j=on * math.cos(th),
                             ji=-on * math.sin(th) if travelling else 0.0))
            rects.append(dict(x0=xc - 0.4 * w, x1=xc + 0.4 * w, y0=y - t / 2, y1=y + t / 2,
                              mat=name, mesh=t, group=1))
    return rects, mats


def sheet_factors(name, stack, work, layers=2, freq=0.0, base=None):
    """(sum of A.J over sheets solved alone, A.J with all sheets driven).
    Divided by the same pair for `base` when given."""
    tag = f"{name}.sheet{layers}" + (".ac" if freq else "")
    ys = sheet_ys(layers)
    alone = sum(run_femm(build_case(f"{tag}.{s}", stack, sheet_rects([y]), freq=freq),
                         work)["AJ_sources_re"] for s, y in enumerate(ys))
    together = run_femm(build_case(f"{tag}.all", stack, sheet_rects(ys), freq=freq),
                        work)["AJ_sources_re"]
    if base:
        return alone / base[0], together / base[1]
    return alone, together


def magnet_rects(on=True):
    w = G["magnet_width_mm"]
    hc = G["remanence_t"] / MU0 if on else 0.0
    mats = [dict(name="magnet", mu=1.0, hc=hc)]
    rects = [dict(x0=xc - w / 2, x1=xc + w / 2, y0=Y_MAG0, y1=Y_MAG1, mat="magnet",
                  mesh=0.1, group=3, magdir=d) for xc, d in ((-TAU / 2, 90), (TAU / 2, 270))]
    # The magnets fill the band height, so the air between them and at the
    # right edge are separate regions.
    ym = (Y_MAG0 + Y_MAG1) / 2
    labels = [dict(x=0.0, y=ym, mat="air", mesh=0.15, group=0),
              dict(x=PERIOD / 2 - 0.01, y=ym, mat="air", mesh=0.15, group=0)]
    return rects, mats, labels


def upper_bands(top_extra=None):
    bands = [dict(y0=0.0, y1=T_PCB, mat="air", mesh=0.08, group=0),
             dict(y0=T_PCB, y1=Y_MAG0, mat="air", mesh=0.08, group=0),
             dict(y0=Y_MAG0, y1=Y_MAG1, mat="air", mesh=0.15, group=0)]
    y = Y_MAG1
    for b in top_extra or []:
        bands.append(b)
        y = b["y1"]
    bands.append(dict(y0=y, y1=y + FAR, mat="air", mesh=0, group=0))
    return bands


def build_case(name, stack, source, freq=0.0, upper=None, extra_mats=(), nonlinear=False,
               previous=None, extra_lines=()):
    lower, mats = stack_bands(stack, freq, nonlinear)
    labels = []
    if source == "magnets":
        rects, smats, labels = magnet_rects()
    elif isinstance(source, tuple) and len(source) == 3:
        # Magnets (on or off) plus current sheets in the same geometry.
        mag_on, rects, smats = source
        mrects, mmats, labels = magnet_rects(mag_on)
        rects, smats = mrects + rects, mmats + smats
    else:
        rects, smats = source
    bands = lower + (upper or upper_bands())
    mats = [dict(name="air", mu=1.0)] + mats + smats + list(extra_mats)
    lines = [dict(name="pcb_top", y=T_PCB, n=240), dict(name="stack_top", y=0.0, n=240)]
    lines += list(extra_lines)
    points = [dict(name="mag_centre_pcb_top", x=-TAU / 2, y=T_PCB)]
    if source == "magnets":
        # |B| just inside the stack top, for the saturation estimate.
        points += [dict(name=f"top{i}", x=-PERIOD / 2 + (i + 0.5) * PERIOD / PEAK_N, y=-0.01)
                   for i in range(PEAK_N)]
    case = dict(name=name, period=PERIOD, freq=freq, materials=mats, bands=bands,
                rects=rects, labels=labels, lines=lines, points=points)
    if previous:
        case["previous"] = previous
    return case


def run_femm(case, work):
    path = os.path.join(work, case["name"] + ".case.lua")
    text = "case = " + lua(case) + "\n"
    out = os.path.join(work, case["name"] + ".out")
    # Reuse a finished run of the identical case.
    fresh = os.path.exists(path) and os.path.exists(out) and open(path).read() == text
    with open(path, "w") as f:
        f.write(text)
    if not fresh:
        if os.path.exists(out):
            os.remove(out)
        subprocess.run([os.path.join(HERE, "run_femm.sh"), os.path.join(HERE, "solve_case.lua"),
                        path, work], check=True, stdin=subprocess.DEVNULL)
    res = {}
    with open(out) as f:
        for line in f:
            k, v = line.split()
            res[k] = float(v)
    return res


# --------------------------------------------------------------------------
# Rust model
# --------------------------------------------------------------------------

def rust_model(cases, layers=2, **extra):
    geometry = dict(G, copper_layers=layers, pcb_thickness_mm=T_PCB, **extra)
    payload = json.dumps({"geometry": geometry, "cases": [{"name": n, "stack": s} for n, _, s in cases]})
    r = subprocess.run(["cargo", "run", "-q", "-p", "pcbmotorgen-simulation", "--example",
                        "backplane_dump"], input=payload, capture_output=True, text=True,
                       cwd=REPO, check=True)
    return {d["name"]: d for d in map(json.loads, r.stdout.splitlines())}


def exact_sheet_factor(stack, ys):
    """1-D transfer solution for sin current sheets at heights `ys` over one
    linear slab: (sheets alone, all sheets driven), or None."""
    if stack["housing"] or len(stack["layers"]) != 1:
        return None
    lay = stack["layers"][0]
    mu = LAYER[lay["material"]][0]
    k = math.pi / TAU
    x = math.exp(-2 * k * lay["thickness_m"] * 1e3)
    r = (mu - 1) / (mu + 1)
    refl = r * (1 - x) / (1 - r * r * x)
    alone = 1 + refl * sum(math.exp(-2 * k * y) for y in ys) / len(ys)
    image = sum(math.exp(-k * (a + b)) for a in ys for b in ys)
    free = sum(math.exp(-k * abs(a - b)) for a in ys for b in ys)
    return alone, 1 + refl * image / free


# --------------------------------------------------------------------------
# Benchmark winding slice from the DXF
# --------------------------------------------------------------------------

def read_dxf_traces(path):
    """Copper segments [(layer, phase, (x0, y0), (x1, y1))] and via points."""
    with open(path) as f:
        raw = f.read().splitlines()
    pairs = [(raw[i].strip(), raw[i + 1].strip()) for i in range(0, len(raw) - 1, 2)]
    ents, cur = [], None
    for code, val in pairs:
        if code == "0":
            if cur:
                ents.append(cur)
            cur = {"type": val}
        elif cur is not None:
            cur.setdefault(code, val)
            if code in ("10", "20"):
                cur.setdefault("pts", []).append(val)
    if cur:
        ents.append(cur)
    rnd = lambda v: round(float(v), 3)
    segs, vias, poly = [], set(), None
    for e in ents:
        lay = e.get("8", "")
        if e["type"] == "LINE":
            a, b = (rnd(e["10"]), rnd(e["20"])), (rnd(e["11"]), rnd(e["21"]))
            if lay.startswith("Via"):
                vias.add(a)
            elif lay[:1] == "L":
                segs.append((lay[:2], lay[-1], a, b))
        elif e["type"] == "POLYLINE":
            poly = [lay, []]
        elif e["type"] == "VERTEX" and poly is not None:
            poly[1].append((rnd(e["10"]), rnd(e["20"])))
        elif e["type"] == "SEQEND" and poly is not None:
            lay, pts = poly
            for a, b in zip(pts, pts[1:]):
                segs.append((lay[:2], lay[-1], a, b))
            poly = None
    return segs, vias


def solve_phase(segs, vias, phase):
    """Unit current terminal -> star through a resistive net (R ~ length,
    vias ideal). Returns edge currents along (a -> b)."""
    key = lambda lay, p: p if p in vias else (lay, p)
    edges = [(key(l, a), key(l, b), a, b, l) for l, ph, a, b in segs if ph == phase]
    nodes = sorted({e[0] for e in edges} | {e[1] for e in edges}, key=str)
    idx = {n: i for i, n in enumerate(nodes)}
    deg = [0] * len(nodes)
    for e in edges:
        deg[idx[e[0]]] += 1
        deg[idx[e[1]]] += 1
    ends = [n for n in nodes if deg[idx[n]] == 1]
    star = [n for n in ends if (n[1] if isinstance(n[0], str) else n) == (6.333, 8.444)]
    term = [n for n in ends if n not in star]
    assert len(star) == 1 and len(term) == 1, (phase, ends)
    n = len(nodes)
    gmat = [[0.0] * n for _ in range(n)]
    for na, nb, a, b, _ in edges:
        g = 1.0 / math.dist(a, b)
        i, j = idx[na], idx[nb]
        gmat[i][i] += g; gmat[j][j] += g; gmat[i][j] -= g; gmat[j][i] -= g
    rhs = [0.0] * n
    rhs[idx[term[0]]] = 1.0
    s = idx[star[0]]  # ground the star
    keep = [i for i in range(n) if i != s]
    a = [[gmat[i][j] for j in keep] + [rhs[i]] for i in keep]
    m = len(keep)
    for c in range(m):
        p = max(range(c, m), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        for r in range(m):
            if r != c and a[r][c]:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    v = [0.0] * n
    for c, i in enumerate(keep):
        v[i] = a[c][m] / a[c][c]
    return [((v[idx[na]] - v[idx[nb]]) * (1.0 / math.dist(a_, b_)), a_, b_, l)
            for na, nb, a_, b_, l in edges]


def winding_slice(dxf, y_cut, x_centre, trace_w):
    """Conductor rectangles of one period, centred on x_centre (DXF mm), with
    the current through the cut y = y_cut for line-to-line A(+1) / B(-1)."""
    segs, vias = read_dxf_traces(dxf)
    cond = []
    for phase, sign in (("A", 1.0), ("B", -1.0), ("C", 0.0)):
        for i_ab, a, b, lay in solve_phase(segs, vias, phase):
            if (a[1] - y_cut) * (b[1] - y_cut) >= 0:
                continue
            t = (y_cut - a[1]) / (b[1] - a[1])
            x = a[0] + t * (b[0] - a[0])
            i_y = i_ab * (1 if b[1] > a[1] else -1)  # current crossing the cut in +y
            cos_t = abs(b[1] - a[1]) / math.dist(a, b)
            cond.append(dict(x=x - x_centre, layer=lay, phase=phase, i=i_y, sign=sign,
                             w=trace_w / cos_t))
    win = [c for c in cond if -PERIOD / 2 < c["x"] <= PERIOD / 2]
    # Periodicity check: the same pattern one period to the right.
    nxt = sorted((round(c["x"] - PERIOD, 3), c["layer"], c["phase"], round(c["i"], 3))
                 for c in cond if PERIOD / 2 < c["x"] <= 1.5 * PERIOD)
    this = sorted((round(c["x"], 3), c["layer"], c["phase"], round(c["i"], 3)) for c in win)
    assert this == nxt, "winding is not periodic over this window"
    return win


def copper_y0(layers, cu_t=0.035):
    """Bottom face of each copper sheet for the DXF layers. Two layers: L1 on
    the PCB bottom, L0 on the top. Four layers (sheets at 0, T/3, 2T/3, T):
    the L1 pattern on the lower two sheets and the L0 pattern on the upper two,
    each conductor carrying its 2-layer current."""
    if layers == 2:
        return {"L1": [0.0], "L0": [T_PCB - cu_t]}
    assert layers == 4
    return {"L1": [0.0, T_PCB / 3 - cu_t / 2], "L0": [2 * T_PCB / 3 - cu_t / 2, T_PCB - cu_t]}


def slice_case(name, win, stack, cu_t=0.035, mode="ll", yoke=None, layers=2):
    rects, mats = [], []
    ys = copper_y0(layers, cu_t)
    for k, c in enumerate(win):
        cur = c["i"] * (c["sign"] if mode == "ll" else (1.0 if c["phase"] == "A" else 0.0))
        area = c["w"] * cu_t  # mm^2
        mname = f"cu{k}"
        mats.append(dict(name=mname, mu=1.0, j=cur / area))  # A/mm^2 = MA/m^2
        assert -PERIOD / 2 + 0.02 < c["x"] - c["w"] / 2 and c["x"] + c["w"] / 2 < PERIOD / 2 - 0.02
        for y0 in ys[c["layer"]]:
            rects.append(dict(x0=c["x"] - c["w"] / 2, x1=c["x"] + c["w"] / 2, y0=y0, y1=y0 + cu_t,
                              mat=mname, mesh=cu_t / 2, group=1))
    extra, top = [], None
    if yoke:
        y_bot, t, mu = yoke
        extra = [dict(name="yoke", mu=mu)]
        upper = [dict(y0=0.0, y1=T_PCB, mat="air", mesh=0.08, group=0),
                 dict(y0=T_PCB, y1=y_bot, mat="air", mesh=0.08, group=0),
                 dict(y0=y_bot, y1=y_bot + t, mat="yoke", mesh=0.2, group=0),
                 dict(y0=y_bot + t, y1=y_bot + t + FAR, mat="air", mesh=0, group=0)]
        top = upper
    return build_case(name, stack, (rects, mats), upper=top, extra_mats=extra)


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=os.path.expanduser("~/.local/opt/femm-runs/t707"))
    ap.add_argument("--dxf", default=os.path.join(REPO, "motor-coils_3s_0-4mm_star.dxf"))
    ap.add_argument("--trace-mm", type=float, default=0.2)
    ap.add_argument("--new-only", action="store_true",
                    help="run only the saturation and eddy-current section")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    if args.new_only:
        saturation_and_eddy(args.work)
        return

    # The FEMM runs in this part are linear, so the model runs without
    # saturation too.
    model = rust_model(CASES, linear=True, freqs_hz=[0.0])
    femm = {}
    base_sheet = sheet_factors("none", CASES[0][2], args.work)
    base_ac = sheet_factors("none", CASES[0][2], args.work, freq=PWM_HZ)
    for name, _, stack in CASES:
        femm[name] = {
            "sheet": sheet_factors(name, stack, args.work, base=base_sheet),
            "mag": run_femm(build_case(f"{name}.mag", stack, "magnets"), args.work),
        }
        if name in AC_CASES:
            femm[name]["ac"] = sheet_factors(name, stack, args.work, freq=PWM_HZ, base=base_ac)
        print(f"done {name}", file=sys.stderr)

    base = femm["none"]
    w = G["magnet_width_mm"] * 1e-3
    rows_l, rows_f = [], []
    for name, label, stack in CASES:
        m, f = model[name], femm[name]
        a = m["analysis"]
        alone, together = f["sheet"]
        exact = exact_sheet_factor(stack, sheet_ys(2))
        ac = f"{f['ac'][0]:.3f}" if "ac" in f else ""
        err = (a["inductance_factor"] - alone) / alone * 100
        rows_l.append(f"| {label} | {a['image_strength']:.3f} | {a['inductance_factor']:.3f} | "
                      f"{alone:.3f} | {'' if exact is None else f'{exact[0]:.3f}'} | {err:+.1f} % | "
                      f"{together:.3f} | {'' if exact is None else f'{exact[1]:.3f}'} | {ac} |")
        # Attraction as mean pressure over the magnet footprint [kPa].
        p_model = a["attraction_n"] / m["magnet_area_m2"] / 1e3
        p_femm = f["mag"].get("Fy_stack", 0.0) / (2 * w * 1.0) / 1e3
        p_err = "" if abs(p_femm) < 0.05 else f"{(p_model - p_femm) / p_femm * 100:+.0f} %"
        fr_femm = f["mag"]["mag_centre_pcb_top_By"] / base["mag"]["mag_centre_pcb_top_By"]
        fr_err = (m["field_ratio_2d"] - fr_femm) / fr_femm * 100
        peak_femm = max(math.hypot(f["mag"][f"top{i}_Bx"], f["mag"][f"top{i}_By"]) for i in range(PEAK_N))
        # Only a magnetic layer 1 sits at the sampled stack top. FEMM is
        # linear here, so compare the model's linear peak.
        peak_model = a["layer_peak_b_t"][0] and a["layer_states"][0]["linear_peak_b_t"] if stack["layers"] else 0.0
        peak = f"{peak_model:.3f} | {peak_femm:.3f}" if peak_model > 0 else " | "
        rows_f.append(f"| {label} | {p_model:.1f} | {p_femm:.1f} | {p_err} | "
                      f"{m['field_ratio_2d']:.3f} | {fr_femm:.3f} | {fr_err:+.1f} % | "
                      f"{-(f['mag']['Fy_magnets'] - base['mag']['Fy_magnets']) / (2 * w) / 1e3:.1f} | {peak} |")

    print("\n### Inductance factor (2 sin current sheets, PCB bottom and top)\n")
    print("| Stack | model K | model factor | FEMM, sheets alone | exact 1-D | model error | "
          "FEMM, sheets together | exact 1-D | FEMM 100 kHz, alone |")
    print("|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows_l))

    # 4 copper layers, MnZn 2 mm: sheets at 0, T/3, 2T/3, T.
    mnzn = next(c for c in CASES if c[0] == "mnzn_2")
    m4 = rust_model([mnzn], layers=4, linear=True)["mnzn_2"]["analysis"]
    alone, together = sheet_factors("mnzn_2", mnzn[2], args.work, layers=4,
                                    base=sheet_factors("none", CASES[0][2], args.work, layers=4))
    exact = exact_sheet_factor(mnzn[2], sheet_ys(4))
    print("\n### Inductance factor, 4 sheets (0, T/3, 2T/3, T), MnZn 2 mm\n")
    print("| model factor | FEMM, sheets alone | exact 1-D | model error | FEMM, sheets together | exact 1-D |")
    print("|---|---|---|---|---|---|")
    print(f"| {m4['inductance_factor']:.3f} | {alone:.3f} | {exact[0]:.3f} | "
          f"{(m4['inductance_factor'] - alone) / alone * 100:+.1f} % | {together:.3f} | {exact[1]:.3f} |")
    print("\n### Attraction and field (alternating magnet row)\n")
    print("| Stack | model p [kPa] | FEMM p [kPa] | p error | model B ratio | FEMM B ratio | B error | "
          "FEMM p, magnet-side check [kPa] | model peak B, layer 1 [T] | FEMM peak B, stack top [T] |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows_f))
    b_plane = base["mag"]["stack_top_By1"]
    print(f"\nField at the stack face (no stack), fundamental: FEMM {b_plane:.4f} T, "
          f"model B0 {model['none']['analysis']['b0_t']:.4f} T")

    # ---- Benchmark winding slice ---------------------------------------
    win = winding_slice(args.dxf, y_cut=3.9, x_centre=45.667, trace_w=args.trace_mm)
    print(f"\n### Benchmark winding slice ({len(win)} conductors per period, trace {args.trace_mm} mm)\n")
    for c in sorted(win, key=lambda c: (c["layer"], c["x"])):
        print(f"<!-- {c['layer']} {c['phase']} x={c['x']:+.3f} I={c['i']:+.3f} -->")
    none = {"layers": [], "housing": None}
    mnzn2 = {"layers": [layer("mn_zn_ferrite", 2.0)], "housing": None}
    mnzn5 = {"layers": [layer("mn_zn_ferrite", 5.0)], "housing": None}
    gap_mnzn2 = {"layers": [layer("fr4", 0.1), layer("mn_zn_ferrite", 2.0)], "housing": None}
    ideal = {"layers": [{"material": "ideal", "thickness_m": 0.02}], "housing": None}
    LAYER["ideal"] = (1e5, 0.0)
    runs = [
        ("MnZn 2 mm, L1 copper on the ferrite", mnzn2, {}),
        ("MnZn 2 mm under a 0.1 mm mask/adhesive gap", gap_mnzn2, {}),
        ("MnZn 5 mm", mnzn5, {}),
        ("mu_r 1e5, 20 mm (one-sided limit)", ideal, {}),
        ("MnZn 2 mm + steel yoke on the magnet backs (y = 5.1 mm)", mnzn2, {"yoke": (Y_MAG1, 2.0, 800.0)}),
        ("MnZn 2 mm + mu_r 1e5 yoke 1.0 mm above the PCB", mnzn2, {"yoke": (T_PCB + 1.0, 2.0, 1e5)}),
        ("MnZn 2 mm + mu_r 1e5 yoke 0.5 mm above the PCB", mnzn2, {"yoke": (T_PCB + 0.5, 2.0, 1e5)}),
        ("MnZn 2 mm + mu_r 1e5 yoke 0.3 mm above the PCB", mnzn2, {"yoke": (T_PCB + 0.3, 2.0, 1e5)}),
    ]
    # The model has no yoke and no mu_r 1e5 material, so only the first rows
    # get a model value.
    slice_model = {2: rust_model([("0", "", mnzn2), ("1", "", gap_mnzn2), ("2", "", mnzn5)], linear=True),
                   4: rust_model([("0", "", mnzn2)], layers=4, linear=True)}
    kk = math.pi / TAU
    print("| Slice | layers | FEMM L-L factor | FEMM phase-A factor | model, midplane | model, layered | layered error (L-L) |")
    print("|---|---|---|---|---|---|---|")
    for layers, rows in ((2, runs), (4, runs[:1])):
        ref = {mode: run_femm(slice_case(f"slice.none.{mode}" + ("" if layers == 2 else f".n{layers}"),
                                         win, none, mode=mode, layers=layers),
                              args.work)["AJ_sources_re"] for mode in ("ll", "a")}
        for k, (label, stack, kw) in enumerate(rows):
            out = []
            for mode in ("ll", "a"):
                tag = f"slice.{k}.{mode}" + ("" if layers == 2 else f".n{layers}")
                r = run_femm(slice_case(tag, win, stack, mode=mode, layers=layers, **kw), args.work)
                out.append(r["AJ_sources_re"] / ref[mode])
            a = slice_model[layers].get(str(k), {}).get("analysis")
            cols = ["", "", ""]
            if a:
                mid = 1 + a["image_strength"] * math.exp(-kk * T_PCB)
                lf = a["inductance_factor"]
                cols = [f"{mid:.3f}", f"{lf:.3f}", f"{(lf - out[0]) / out[0] * 100:+.1f} %"]
            print(f"| {label} | {layers} | {out[0]:.3f} | {out[1]:.3f} | " + " | ".join(cols) + " |")

    saturation_and_eddy(args.work)

# --------------------------------------------------------------------------
# Saturation and eddy currents (tickets 04n2, q9nw)
# --------------------------------------------------------------------------

def set_pcb(t_pcb):
    """Switch the FEMM geometry to a PCB of thickness `t_pcb` [mm]."""
    global T_PCB, Y_MAG0, Y_MAG1
    T_PCB = t_pcb
    Y_MAG0 = T_PCB + G["air_gap_mm"]
    Y_MAG1 = Y_MAG0 + G["magnet_height_mm"]


def err(model, ref, tol):
    """Relative error and pass / fail against `tol` (a fraction)."""
    e = (model - ref) / ref
    return f"{e * 100:+.1f} % | {'pass' if abs(e) <= tol else 'FAIL'}"


def flex(t_mm, **kw):
    return {"layers": [layer("flex_ferrite", t_mm, **kw)], "housing": None}


NONE = {"layers": [], "housing": None}
NL_STACKS = [
    ("flex_0.1", "Flex ferrite 0.1 mm", flex(0.1)),
    ("flex_0.2", "Flex ferrite 0.2 mm (version 2)", flex(0.2)),
    ("flex_1", "Flex ferrite 1 mm", flex(1.0)),
    ("flex_5", "Flex ferrite 5 mm", flex(5.0)),
    ("mnzn_2", "MnZn 2 mm", {"layers": [layer("mn_zn_ferrite", 2.0)], "housing": None}),
    ("mnzn_2.8", "MnZn 2.8 mm", {"layers": [layer("mn_zn_ferrite", 2.8)], "housing": None}),
]
V2_AL = housing("aluminum6061", 1.0, 0.1)


def nonlinear_section(work):
    """Magnet row over saturating layers on the 0.8 mm PCB."""
    set_pcb(0.8)
    model = rust_model(NL_STACKS)
    linear = rust_model(NL_STACKS, linear=True)
    base = run_femm(build_case("v2.none.mag", NONE, "magnets"), work)
    w = G["magnet_width_mm"] * 1e-3
    rows_f, rows_b, rows_k = [], [], []
    for name, label, st in NL_STACKS:
        t = st["layers"][0]["thickness_m"] * 1e3
        mid = [dict(name="sheet_mid", y=-t / 2, n=240)]
        lin = run_femm(build_case(f"v2.{name}.mag", st, "magnets", extra_lines=mid), work)
        nl = run_femm(build_case(f"v2.{name}.nl", st, "magnets", nonlinear=True, extra_lines=mid), work)
        knee = run_femm(build_case(f"v2.{name}.knee", st, "magnets", nonlinear="knee", extra_lines=mid), work)
        m, ml = model[name], linear[name]
        a, s0 = m["analysis"], m["analysis"]["layer_states"][0]
        ratio = lambda f: f["mag_centre_pcb_top_By"] / base["mag_centre_pcb_top_By"]
        press = lambda f: f["Fy_stack"] / (2 * w * 1.0) / 1e3
        p_model = a["attraction_n"] / m["magnet_area_m2"] / 1e3
        p_lin = ml["analysis"]["attraction_n"] / m["magnet_area_m2"] / 1e3
        peak = max(math.hypot(nl[f"top{i}_Bx"], nl[f"top{i}_By"]) for i in range(PEAK_N))
        rows_f.append(f"| {label} | {a['linear_image_strength']:.3f} | {a['image_strength']:.3f} | "
                      f"{m['field_ratio_2d']:.3f} | {ratio(nl):.3f} | {err(m['field_ratio_2d'], ratio(nl), 0.05)} | "
                      f"{ml['field_ratio_2d']:.3f} | {ratio(lin):.3f} | "
                      f"{p_model:.1f} | {press(nl):.1f} | {err(p_model, press(nl), 0.10)} | "
                      f"{p_lin:.1f} | {press(lin):.1f} |")
        rows_b.append(f"| {label} | {s0['flux_overload']:.2f} | {s0['mu_effective']:.1f} | "
                      f"{s0['mean_b_t']:.3f} | {nl['sheet_mid_Bx1']:.3f} | {err(s0['mean_b_t'], nl['sheet_mid_Bx1'], 0.10)} | "
                      f"{s0['peak_b_t']:.3f} | {peak:.3f} | {err(s0['peak_b_t'], peak, 0.10)} | "
                      f"{s0['linear_peak_b_t']:.2f} |")
        rows_k.append(f"| {label} | {m['field_ratio_2d']:.3f} | {ratio(knee):.3f} | {err(m['field_ratio_2d'], ratio(knee), 0.05)} | "
                      f"{p_model:.1f} | {press(knee):.1f} | {err(p_model, press(knee), 0.10)} | "
                      f"{s0['mean_b_t']:.3f} | {knee['sheet_mid_Bx1']:.3f} | {err(s0['mean_b_t'], knee['sheet_mid_Bx1'], 0.10)} |")
    print("\n### Saturation: field and attraction (0.8 mm PCB, magnet row, 1 m deep)\n")
    print("| Stack | model R, linear | model R, saturated | model B ratio | FEMM B ratio, nonlinear | B ratio error | | "
          "model B ratio, linear | FEMM B ratio, linear | model p [kPa] | FEMM p, nonlinear [kPa] | p error | | "
          "model p, linear [kPa] | FEMM p, linear [kPa] |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows_f))
    print("\n### Saturation: flux density in the layer\n")
    print("| Stack | model flux overload | model mu_eff | model mean in-plane B1 [T] | FEMM Bx1 at mid-layer [T] | error | | "
          "model peak [T] | FEMM peak, 0.01 mm inside the face [T] | error | | model linear peak [T] |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows_b))
    print("\n### Saturation with the model's two-slope B-H curve in FEMM\n")
    print("| Stack | model B ratio | FEMM B ratio | error | | model p [kPa] | FEMM p [kPa] | error | | "
          "model mean in-plane B1 [T] | FEMM Bx1 at mid-layer [T] | error | |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows_k))
    return model


INC_STACKS = [s for s in NL_STACKS if s[0] in ("flex_0.2", "flex_1", "mnzn_2")]


def incremental_section(work):
    """Coil sheets with the incremental permeability of the magnet bias."""
    set_pcb(0.8)
    model = rust_model(INC_STACKS, freqs_hz=[0.0])
    ys = sheet_ys(2)
    phases = (("coil flux on the saturated regions", 0.0), ("coil flux on the unsaturated regions", math.pi / 2))
    base = {k: sum(run_femm(build_case(f"v2.inc.none.p{k}.{s}", NONE, sheet_rects([y], phase=ph)), work)
                   ["AJ_sources_re"] for s, y in enumerate(ys))
            for k, (_, ph) in enumerate(phases)}
    rows = []
    for name, label, st in INC_STACKS:
        bias = build_case(f"v2.inc.{name}.bias", st, (True, *sheet_rects(ys, live=())), nonlinear=True)
        run_femm(bias, work)
        tag = hash_text(lua(bias))
        out = []
        for k, (_, ph) in enumerate(phases):
            total = 0.0
            for s in range(len(ys)):
                case = build_case(f"v2.inc.{name}.p{k}.{s}", st, (False, *sheet_rects(ys, phase=ph, live=(s,))),
                                  nonlinear=True, previous=bias["name"])
                case["previous_text"] = tag
                total += run_femm(case, work)["AJ_sources_re"]
            out.append(total / base[k])
        coil = model[name]["coil"][0]
        under, away = coil["under"][0], coil["away"][0]
        mean = sum(out) / 2
        rows.append(f"| {label} | {model[name]['analysis']['layer_states'][0]['mu_incremental']:.2f} | {under:.3f} | "
                    f"{out[0]:.3f} | {out[1]:.3f} | {mean:.3f} | {err(under, mean, 0.05)} | {away:.3f} |")
    print("\n### Inductance under the magnets (incremental permeability, 0.8 mm PCB)\n")
    print("| Stack | model mu_inc | model factor under the magnets | FEMM, " + phases[0][0] + " | FEMM, " + phases[1][0]
          + " | FEMM mean | error vs mean | | model factor away from the magnets |")
    print("|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))


def hash_text(text):
    import hashlib
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def ac_coil_section(work, model_v2):
    """Inductance factor and added resistance at the PWM frequency."""
    mu_inc = model_v2["flex_0.2"]["analysis"]["layer_states"][0]["mu_incremental"]
    groups = [
        (1.6, "", [
            ("al_only", "Al 3 mm @1 mm", {"layers": [], "housing": housing("aluminum6061", 3.0, 1.0)}),
            ("steel_only", "Steel 1018 3 mm @1 mm", {"layers": [], "housing": housing("steel1018", 3.0, 1.0)}),
            ("sisteel_0.35", "Si steel 0.35 mm", {"layers": [layer("silicon_steel", 0.35)], "housing": None}),
            ("mnzn_2+al", "MnZn 2 mm + Al 3 mm @1 mm", {"layers": [layer("mn_zn_ferrite", 2.0)],
                                                       "housing": housing("aluminum6061", 3.0, 1.0)}),
        ]),
        (0.8, "v2.", [
            ("al_1@0.3", "Al 1 mm @0.3 mm (version 2 without the sheet)",
             {"layers": [], "housing": housing("aluminum6061", 1.0, 0.3)}),
            ("away", "Version 2 away from the magnets: flex 0.2 mm (mu 130) + Al 1 mm @0.1 mm",
             {"layers": [layer("flex_ferrite", 0.2)], "housing": V2_AL}),
            ("under", f"Version 2 under the magnets: flex 0.2 mm at the model's mu_inc {mu_inc:.3f} + Al",
             {"layers": [layer("flex_ferrite", 0.2, mu_r=mu_inc)], "housing": V2_AL}),
        ]),
    ]
    rows = []
    for t_pcb, prefix, cases in groups:
        set_pcb(t_pcb)
        model = rust_model(cases, linear=True, freqs_hz=[0.0, PWM_HZ])
        for name, label, st in cases:
            # The 1.6 mm cases reuse the 100 kHz runs of the first table.
            f = ac_alone(prefix + name, st, prefix + "none", work)
            c0, c1 = model[name]["coil"]
            m = complex(*c1["away"])
            rows.append(f"| {label} | {t_pcb} | {c0['away'][0]:.3f} | {m.real:.3f} | {f.real:.3f} | {err(m.real, f.real, 0.05)} | "
                        f"{-m.imag:.4f} | {-f.imag:.4f} | {err(-m.imag, -f.imag, 0.10) if abs(f.imag) > 1e-3 else ' | '} |")
    print("\n### Coil at 100 kHz (2 sin current sheets solved alone, time-harmonic)\n")
    print("Added resistance per phase is `-Im F` times `2*pi*f*L0`.\n")
    print("| Stack | PCB [mm] | model factor, DC | model Re F | FEMM Re F | error | | model -Im F | FEMM -Im F | error | |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))


def ac_alone(name, stack, base, work):
    """Complex inductance factor at 100 kHz: the A.J of the two sheets solved
    alone with the stack, over the same without it. Case names follow the
    first table, so its runs are reused."""
    ys = sheet_ys(2)
    def total(n, st):
        r = [run_femm(build_case(f"{n}.sheet2.ac.{s}", st, sheet_rects([y]), freq=PWM_HZ), work)
             for s, y in enumerate(ys)]
        return complex(sum(x["AJ_sources_re"] for x in r), sum(x["AJ_sources_im"] for x in r))
    return total(name, stack) / total(base, NONE)


def drag_section(work, model_v2):
    """Travelling current sheet over conductive stacks: drag and normal force."""
    mu_eff = model_v2["flex_0.2"]["analysis"]["layer_states"][0]["mu_effective"]
    speeds = [1.0, 20.0, 100.0]
    groups = [
        (1.6, [("al_only", "Al 3 mm @1 mm", {"layers": [], "housing": housing("aluminum6061", 3.0, 1.0)}),
               ("steel_only", "Steel 1018 3 mm @1 mm", {"layers": [], "housing": housing("steel1018", 3.0, 1.0)})]),
        (0.8, [("v2_magnet", f"Version 2: flex 0.2 mm at the model's mu_eff {mu_eff:.2f} + Al 1 mm @0.1 mm",
                {"layers": [layer("flex_ferrite", 0.2, mu_r=mu_eff)], "housing": V2_AL})]),
    ]
    rows = []
    for t_pcb, cases in groups:
        set_pcb(t_pcb)
        model = rust_model(cases, linear=True, speeds_m_s=speeds)
        ys = sheet_ys(2)
        for name, label, st in cases:
            for k, v in enumerate(speeds):
                freq = v / (2 * TAU * 1e-3)
                src = sheet_rects([ys[1]], travelling=True)
                b = run_femm(build_case(f"drag.pcb{t_pcb}.none.v{v:g}", NONE, src, freq=freq), work)
                r = run_femm(build_case(f"drag.pcb{t_pcb}.{name}.v{v:g}", st, src, freq=freq), work)
                q = b["stack_top_By1f"] ** 2 / MU0 * PERIOD * 1e-3 * 1.0
                drag_f, normal_f = r["Fx_stack"] / q, r["Fy_stack"] / q
                refl = model[name]["motion"][k]["reflection"]
                drag_m, normal_m = -refl[1], refl[0]
                balance = r["loss_stack"] / (r["Fx_stack"] * v) if abs(r["Fx_stack"]) > 1e-12 else float("nan")
                rows.append(f"| {label} | {v:g} | {freq:.0f} | {drag_m:.4f} | {drag_f:.4f} | {err(drag_m, drag_f, 0.10)} | "
                            f"{normal_m:+.4f} | {normal_f:+.4f} | {err(normal_m, normal_f, 0.10) if abs(normal_f) > 5e-3 else 'floor | '} | "
                            f"{balance:.3f} |")
    print("\n### Eddy drag of a travelling field (2-D fundamental, per B0^2/mu0 of the bare field at the stack top)\n")
    print("Normal forces below 0.005 are at FEMM's numerical floor (the no-stack rows above give ±0.002).\n")
    print("| Stack | v [m/s] | f [Hz] | model -Im R | FEMM drag | error | | model Re R | FEMM normal | error | | FEMM loss / (F v) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    print("\n".join(rows))


def saturation_and_eddy(work):
    model_v2 = nonlinear_section(work)
    incremental_section(work)
    ac_coil_section(work, model_v2)
    drag_section(work, model_v2)
    set_pcb(G["pcb_thickness_mm"])



if __name__ == "__main__":
    main()
