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
  * inductance: a sinusoidal current sheet (wavenumber pi/tau) at the PCB
    midplane; factor = (A.J with stack) / (A.J without);
  * attraction / field: the alternating magnet row, linear materials.
The benchmark slice cuts the benchmark winding (DXF) at the middle of the board and
reports the line-to-line inductance factor of that copper layout.
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
# so pole pitch tau = 6 mm.
G = dict(pole_pitch_mm=6.0, magnet_width_mm=5.0, magnet_cross_width_mm=5.0,
         magnet_height_mm=3.0, magnet_count=5, remanence_t=1.34,
         air_gap_mm=0.5, pcb_thickness_mm=1.6)
TAU = G["pole_pitch_mm"]
PERIOD = 2 * TAU
T_PCB = G["pcb_thickness_mm"]
Y_MAG0 = T_PCB + G["air_gap_mm"]
Y_MAG1 = Y_MAG0 + G["magnet_height_mm"]
FAR = 40.0  # distance to the A = 0 lines; exp(-pi*40/6) ~ 1e-9
PWM_HZ = 100e3

# Same mu_r as crates/pcbmotorgen-simulation/src/backplane/mod.rs. Conductivity
# [MS/m] is only used by the 100 kHz runs (the model has no eddy currents):
# typical handbook values.
LAYER = {
    "fr4": (1.0, 0.0),
    "silicon_steel": (4000.0, 2.0),
    "mn_zn_ferrite": (2500.0, 1e-6),
    "ni_zn_ferrite": (500.0, 0.0),
    "flex_ferrite": (60.0, 0.0),
}
HOUSING = {
    "aluminum6061": (1.0, 25.0),
    "steel1018": (800.0, 6.0),
}


def layer(material, t_mm):
    return {"material": material, "thickness_m": t_mm * 1e-3}


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


def stack_bands(stack, freq):
    """Bands below y = 0 (bottom to top) and the materials they use."""
    mats, bands = {}, []
    y = 0.0
    for lay in stack["layers"]:
        t = lay["thickness_m"] * 1e3
        mu, sig = LAYER[lay["material"]]
        mats[lay["material"]] = dict(name=lay["material"], mu=mu, sigma=sig if freq else 0.0)
        bands.append(dict(y0=y - t, y1=y, mat=lay["material"] if mu > 1 else "air",
                          mesh=mesh_for(t), group=2 if mu > 1 else 0))
        y -= t
    h = stack["housing"]
    if h:
        gap, t = h["gap_m"] * 1e3, h["thickness_m"] * 1e3
        mu, sig = HOUSING[h["material"]]
        mats[h["material"]] = dict(name=h["material"], mu=mu, sigma=sig if freq else 0.0)
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
            if m and m["sigma"] > 0.1 and b["group"] == 2 and b["mat"] in LAYER:
                delta = 1e3 * math.sqrt(2 / (2 * math.pi * freq * m["mu"] * MU0 * m["sigma"] * 1e6))
                b["mesh"] = max(delta / 3, 0.002)
    bands.reverse()
    bands.insert(0, dict(y0=y - FAR, y1=y, mat="air", mesh=0, group=0))
    bands.sort(key=lambda b: b["y0"])
    return bands, list(mats.values())


def sheet_rects(n=48, y=T_PCB / 2, t=0.02, j0=1.0):
    """Sinusoidal current sheet, wavenumber pi/tau, as n strips."""
    mats, rects = [], []
    w = PERIOD / n
    for i in range(n):
        xc = -PERIOD / 2 + (i + 0.5) * w
        name = f"src{i}"
        mats.append(dict(name=name, mu=1.0, j=j0 * math.cos(math.pi * xc / TAU)))
        rects.append(dict(x0=xc - 0.4 * w, x1=xc + 0.4 * w, y0=y - t / 2, y1=y + t / 2,
                          mat=name, mesh=t, group=1))
    return rects, mats


def magnet_rects():
    w = G["magnet_width_mm"]
    hc = G["remanence_t"] / MU0
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


def build_case(name, stack, source, freq=0.0, upper=None, extra_mats=()):
    lower, mats = stack_bands(stack, freq)
    labels = []
    if source == "sheet":
        rects, smats = sheet_rects()
    elif source == "magnets":
        rects, smats, labels = magnet_rects()
    else:
        rects, smats = source
    bands = lower + (upper or upper_bands())
    mats = [dict(name="air", mu=1.0)] + mats + smats + list(extra_mats)
    lines = [dict(name="pcb_top", y=T_PCB, n=240), dict(name="stack_top", y=0.0, n=240)]
    points = [dict(name="mag_centre_pcb_top", x=-TAU / 2, y=T_PCB)]
    return dict(name=name, period=PERIOD, freq=freq, materials=mats, bands=bands,
                rects=rects, labels=labels, lines=lines, points=points)


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

def rust_model(cases):
    payload = json.dumps({"geometry": G, "cases": [{"name": n, "stack": s} for n, _, s in cases]})
    r = subprocess.run(["cargo", "run", "-q", "-p", "pcbmotorgen-simulation", "--example",
                        "backplane_dump"], input=payload, capture_output=True, text=True,
                       cwd=REPO, check=True)
    return {d["name"]: d for d in map(json.loads, r.stdout.splitlines())}


def exact_sheet_factor(stack):
    """1-D transfer solution for a sin current sheet over one linear slab."""
    if stack["housing"] or len(stack["layers"]) != 1:
        return None
    lay = stack["layers"][0]
    mu = LAYER[lay["material"]][0]
    k = math.pi / TAU
    x = math.exp(-2 * k * lay["thickness_m"] * 1e3)
    r = (mu - 1) / (mu + 1)
    refl = r * (1 - x) / (1 - r * r * x)
    return 1 + refl * math.exp(-2 * k * T_PCB / 2)


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


def slice_case(name, win, stack, cu_t=0.035, mode="ll", yoke=None):
    rects, mats = [], []
    for k, c in enumerate(win):
        cur = c["i"] * (c["sign"] if mode == "ll" else (1.0 if c["phase"] == "A" else 0.0))
        area = c["w"] * cu_t  # mm^2
        mname = f"cu{k}"
        mats.append(dict(name=mname, mu=1.0, j=cur / area))  # A/mm^2 = MA/m^2
        y0 = T_PCB - cu_t if c["layer"] == "L0" else 0.0
        assert -PERIOD / 2 + 0.02 < c["x"] - c["w"] / 2 and c["x"] + c["w"] / 2 < PERIOD / 2 - 0.02
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
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)

    model = rust_model(CASES)
    femm = {}
    for name, _, stack in CASES:
        femm[name] = {
            "sheet": run_femm(build_case(f"{name}.sheet", stack, "sheet"), args.work),
            "mag": run_femm(build_case(f"{name}.mag", stack, "magnets"), args.work),
        }
        if name in AC_CASES:
            femm[name]["ac"] = run_femm(build_case(f"{name}.ac", stack, "sheet", freq=PWM_HZ), args.work)
        print(f"done {name}", file=sys.stderr)

    base = femm["none"]
    w = G["magnet_width_mm"] * 1e-3
    rows_l, rows_f = [], []
    for name, label, stack in CASES:
        m, f = model[name], femm[name]
        a = m["analysis"]
        lf_femm = f["sheet"]["AJ_sources_re"] / base["sheet"]["AJ_sources_re"]
        exact = exact_sheet_factor(stack)
        ac = ""
        if "ac" in f:
            ac = f"{f['ac']['AJ_sources_re'] / base['ac']['AJ_sources_re']:.3f}"
        err = (a["inductance_factor"] - lf_femm) / lf_femm * 100
        rows_l.append(f"| {label} | {a['image_strength']:.3f} | {a['inductance_factor']:.3f} | "
                      f"{lf_femm:.3f} | {'' if exact is None else f'{exact:.3f}'} | {err:+.1f} % | {ac} |")
        # Attraction as mean pressure over the magnet footprint [kPa].
        p_model = a["attraction_n"] / m["magnet_area_m2"] / 1e3
        p_femm = f["mag"].get("Fy_stack", 0.0) / (2 * w * 1.0) / 1e3
        p_err = "" if abs(p_femm) < 0.05 else f"{(p_model - p_femm) / p_femm * 100:+.0f} %"
        fr_femm = f["mag"]["mag_centre_pcb_top_By"] / base["mag"]["mag_centre_pcb_top_By"]
        fr_err = (m["field_ratio_2d"] - fr_femm) / fr_femm * 100
        rows_f.append(f"| {label} | {p_model:.1f} | {p_femm:.1f} | {p_err} | "
                      f"{m['field_ratio_2d']:.3f} | {fr_femm:.3f} | {fr_err:+.1f} % | "
                      f"{-(f['mag']['Fy_magnets'] - base['mag']['Fy_magnets']) / (2 * w) / 1e3:.1f} |")

    print("\n### Inductance factor (sin current sheet at the PCB midplane)\n")
    print("| Stack | model K | model factor | FEMM factor | exact 1-D | model error | FEMM 100 kHz |")
    print("|---|---|---|---|---|---|---|")
    print("\n".join(rows_l))
    print("\n### Attraction and field (alternating magnet row)\n")
    print("| Stack | model p [kPa] | FEMM p [kPa] | p error | model B ratio | FEMM B ratio | B error | FEMM p, magnet-side check [kPa] |")
    print("|---|---|---|---|---|---|---|---|")
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
    print("| Slice | FEMM L-L factor | FEMM phase-A factor |")
    print("|---|---|---|")
    ref = {mode: run_femm(slice_case(f"slice.none.{mode}", win, none, mode=mode),
                          args.work)["AJ_sources_re"] for mode in ("ll", "a")}
    for k, (label, stack, kw) in enumerate(runs):
        out = []
        for mode in ("ll", "a"):
            r = run_femm(slice_case(f"slice.{k}.{mode}", win, stack, mode=mode, **kw), args.work)
            out.append(r["AJ_sources_re"] / ref[mode])
        print(f"| {label} | {out[0]:.3f} | {out[1]:.3f} |")


if __name__ == "__main__":
    main()
