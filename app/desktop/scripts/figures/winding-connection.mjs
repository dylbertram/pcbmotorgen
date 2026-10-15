// Builds the winding-connection figure: a motor terminal box whose brass
// links set how the three phase windings are joined. One SVG carries all
// three link layouts; the app shows one at a time through `data-mode`.
//
//   node scripts/figures/winding-connection.mjs            writes the app assets
//   node scripts/figures/winding-connection.mjs --preview  also writes preview pages to /tmp/winding-connection
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ASSETS = join(HERE, "../../src/lib/assets");
const WIDTH = 600;
const HEIGHT = 360;

// --- World layout (units ≈ 1 px; x along the block, y toward the viewer, z up)
const PLATE = { x: -106, y: -72, w: 212, d: 160, r: 8 };
const PLATE_H = 12;
const FOOT_H = 5;

const COL = [-30, 0, 30];
const PHASES = ["A", "B", "C"];
const COIL_Y = -44;
const COIL_X = [-72, 0, 72];
const COIL_R = 15;
const FLANGE_R = 19;
const COIL_Z0 = 6;
const COIL_Z1 = 36;
const COIL_TOP = COIL_Z1 + 3;

const BLOCK = { x: -52, y: 2, w: 104, d: 56, r: 3 };
const BLOCK_H = 10;
const ROW_BACK = 16;
const ROW_FRONT = 44;
const BOSS_H = 2;
const WASHER_Z = BLOCK_H + BOSS_H;
const LUG_Z = WASHER_Z + 1;
const LINK_Z = LUG_Z + 0.7;
const NUT_Z = LINK_Z + 1.3;
const NUT_H = 3;
const TIP_H = 3.4;

const GLAND_Y = 74;
const GLAND_Z = 7;

// IEC terminal layout: phase X runs from X1 (front row) to X2 (back row).
// Back row reads C2 A2 B2, front row A1 B1 C1, so delta links are straight
// and the star bar runs across the back row.
const FRONT = PHASES.map((_, i) => [COL[i], ROW_FRONT]);
const BACK = [2, 0, 1];
const backOf = (phase) => [COL[BACK.indexOf(phase)], ROW_BACK];

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [COIL_X[0], COIL_Y, COIL_TOP + 14], [COIL_X[2], COIL_Y, COIL_TOP + 14]],
  WIDTH,
  HEIGHT,
  { pad: 22, azimuth: 64 },
);

const at = (point) => k.iso(point, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const depth2 = ([x, y]) => k.depthOf([x, y, 0], P);
const byDepth = (points) => [...points].sort((a, b) => depth2(a) - depth2(b));
const show = (modes, body) => `<g data-show="${modes}">${body}</g>`;

// --- Base plate --------------------------------------------------------------
function plate() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 22))) {
    out.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
  const screws = k.corners(PLATE, 10);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.2, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));

  // Label plate, front right: three rule lines for its printed text.
  const label = { x: 56, y: 64, w: 38, d: 18, r: 1.5 };
  out.push(S(k.slabOf(label, 0, 0.8, P, 4), { tone: "lo", crease: "none" }));
  out.push(L(k.planOutline(k.insetPlan(label, 1.6), 0.8, P, 4), { tone: "faint" }));
  [[30, 6.5], [22, 11], [26, 15.5]].forEach(([w, y]) => {
    out.push(L(k.lineOnTop([label.x + 6, label.y + y], [label.x + 6 + w, label.y + y], 0.8, P), { tone: "lo", free: true }));
  });
  out.push(D([at([label.x + 3, label.y + 3, 0.8]), at([label.x + label.w - 3, label.y + label.d - 3, 0.8])], { size: 0.45 }));
  return out.join("");
}

// --- Coils on their mounting pads -------------------------------------------
// Leads leave through two eyelets on the bottom flange, facing the block.
const exitOf = (i, side) => [COIL_X[i] + side * 7, COIL_Y + 15.6, COIL_Z0];

function eyelets(i) {
  return [-1, 1].map((side) => {
    const [x, y, z] = exitOf(i, side);
    return S(k.cylinder(x, y, 1.8, z, 0.8, P, 16), { tone: "mid" }) + L(k.ring(x, y, 0.8, z + 0.8, P, 10), { tone: "lo" });
  }).join("");
}

function coil(i) {
  const cx = COIL_X[i];
  const cy = COIL_Y;
  const out = [];
  const pad = { x: cx - 24, y: cy - 24, w: 48, d: 48, r: 3 };
  out.push(S(k.slabOf(pad, 0, 3, P, 4, 0.5), { tone: "mid" }));
  const screws = k.corners(pad, 5);
  out.push(D(screws.map(([x, y]) => at([x, y, 3])), { size: 0.5 }));
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 1.6, 3, P, 12)).join(""), { tone: "lo" }));
  out.push(S(k.cylinder(cx, cy, FLANGE_R, 3, COIL_Z0 - 3, P, 56, 0.5), { tone: "mid" }));
  // The winding: wire turns are faint bands round the visible half.
  const turns = [];
  for (let z = COIL_Z0 + 2.5; z < COIL_Z1 - 1; z += 2.6) turns.push(k.sideArc(cx, cy, COIL_R, z, P, 40));
  out.push(S(k.cylinder(cx, cy, COIL_R, COIL_Z0, COIL_Z1 - COIL_Z0, P, 56), {
    tone: "hi",
    crease: "lo",
    inner: L(turns.join(""), { tone: "faint" }),
  }));
  out.push(S(k.cylinder(cx, cy, FLANGE_R, COIL_Z1, 3, P, 56, 0.5), { tone: "mid" }));
  out.push(L(k.ring(cx, cy, FLANGE_R - 3, COIL_TOP, P, 48), { tone: "faint" }));
  // Core bolt through the bore.
  out.push(S(k.cylinder(cx, cy, 6, COIL_TOP, 1.2, P, 28), { tone: "lo" }));
  out.push(S(k.cylinder(cx, cy, 4, COIL_TOP + 1.2, 2.6, P, 6), { tone: "mid" }));
  out.push(L(k.ring(cx, cy, 1.4, COIL_TOP + 3.8, P, 12), { tone: "lo" }));
  // Core bolt and the phase letter sit on the top flange.
  // Engraved phase letter on the flange.
  out.push(k.faceTextSvg(k.topMatrix([cx, cy - 12], COIL_TOP, P, "x"), PHASES[i], { size: 4, tone: "lo", anchor: "middle" }));
  return out.join("");
}

// --- Terminal block ------------------------------------------------------------
function block() {
  const out = [];
  out.push(`<path class="iso-halo" d="${k.haloOf(k.insetPlan(BLOCK, 2), 0, 1, P)}" style="filter:blur(4px)"/>`);
  out.push(S(k.slabOf(BLOCK, 0, BLOCK_H, P, 4, 0.8), { tone: "mid", inner: L(k.sideSeam(BLOCK, 3, P, 4), { tone: "faint" }) }));
  out.push(L(k.planOutline(k.insetPlan(BLOCK, 3), BLOCK_H, P, 4), { tone: "faint" }));
  // Fixing screws in the four corners of the block.
  const screws = k.corners(BLOCK, 4.5);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 1.8, BLOCK_H, P, 12)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, BLOCK_H])), { size: 0.5 }));
  return out.join("");
}

const STUDS = byDepth([...FRONT, ...PHASES.map((_, i) => backOf(i))]);

// Each stud stands on a raised insulating boss, with a flat washer on top.
const washers = () => STUDS.map(([x, y]) => S(k.cylinder(x, y, 6.4, BLOCK_H, BOSS_H, P, 32, 0.4), { tone: "mid" })
  + S(k.cylinder(x, y, 4.6, WASHER_Z, 1, P, 28), { tone: "lo" })).join("");

function nut([x, y]) {
  return [
    S(k.cylinder(x, y, 4, NUT_Z, NUT_H, P, 6, 0.3), { tone: "mid" }),
    S(k.cylinder(x, y, 1.9, NUT_Z + NUT_H, TIP_H, P, 16), {
      tone: "mid",
      crease: "none",
      inner: L([0.9, 1.8, 2.7].map((dz) => k.sideArc(x, y, 1.9, NUT_Z + NUT_H + dz, P, 12)).join(""), { tone: "lo" }),
    }),
  ].join("");
}

// A ring lug under a nut, its tongue pointing along `dir` (floor vector). The
// crimp barrel at the tongue end stands on the block, and the wire enters it
// at its foot.
const TONGUE = 9;
function lug([x, y], dir, z = LUG_Z) {
  const [dx, dy] = dir;
  const tx = x + dx * TONGUE;
  const ty = y + dy * TONGUE;
  const plan = dx
    ? { x: Math.min(x, tx), y: y - 1.6, w: Math.abs(tx - x), d: 3.2, r: 1.2 }
    : { x: x - 1.6, y: Math.min(y, ty), w: 3.2, d: Math.abs(ty - y), r: 1.2 };
  return [
    S(k.cylinder(tx, ty, 1.6, BLOCK_H, z + 0.7 - BLOCK_H, P, 14), { tone: "mid", inner: L(k.sideArc(tx, ty, 1.6, BLOCK_H + 1.2, P, 10), { tone: "faint" }) }),
    S(k.slabOf(plan, z, 0.7, P, 3), { tone: "mid", crease: "none" }),
    S(k.cylinder(x, y, 3.6, z, 0.7, P, 24), { tone: "mid", crease: "none" }),
  ].join("");
}
const tongueEnd = ([x, y], [dx, dy]) => [x + dx * TONGUE, y + dy * TONGUE, BLOCK_H + 0.4];

// Coil lead lugs point toward -x into the gap beside each stud.
const LEAD_DIR = [-1, 0];

// Supply lugs point to the front, toward the cable glands.
const SUPPLY_DIR = [0, 1];

// --- Brass links ----------------------------------------------------------------
function link(a, b) {
  const [x0, y0] = a;
  const [x1, y1] = b;
  const plan = x0 === x1
    ? { x: x0 - 3.4, y: Math.min(y0, y1) - 4, w: 6.8, d: Math.abs(y1 - y0) + 8, r: 3.2 }
    : { x: Math.min(x0, x1) - 4, y: y0 - 3.4, w: Math.abs(x1 - x0) + 8, d: 6.8, r: 3.2 };
  return S(k.slabOf(plan, LINK_Z, 1.3, P, 6, 0.3), { tone: "hi", lit: true });
}

const deltaLinks = () => byDepth(PHASES.map((_, i) => [COL[i], (ROW_BACK + ROW_FRONT) / 2]))
  .map(([x]) => link([x, ROW_BACK], [x, ROW_FRONT]))
  .join("");
const starBar = () => link([COL[0], ROW_BACK], [COL[2], ROW_BACK]);

// --- Wires ----------------------------------------------------------------------
// Coil leads leave the bottom-flange eyelets, drop onto the pad, lie along
// the plate to the back of the block, climb it and run across its top to the
// lug. Each lead is two paths: the floor run is painted before the block, the
// top run after it.
const LEAD_Z = 0.6;
const PAD_Z = 3.6;
const CLIMB_Y = BLOCK.y + 1.2;

function leadPaths(i, side, end) {
  const [ex, ey, ez] = exitOf(i, side);
  const x = end[0];
  const floor = [
    [ex, ey, ez + 0.8],
    [ex, ey + 4.4, PAD_Z],
    [ex, COIL_Y + 25, PAD_Z],
    [ex, COIL_Y + 27, LEAD_Z],
    [x, BLOCK.y - 6, LEAD_Z],
    [x, BLOCK.y - 0.2, LEAD_Z],
  ];
  const top = [[x, CLIMB_Y, BLOCK_H + 0.4], [x, end[1], BLOCK_H + 0.4], end];
  return { floor, top };
}

const wire = (points, ends) => k.wireSvg(at(points[0]), at(points[points.length - 1]), {
  via: points.slice(1, -1).map(at),
  tone: "hi",
  size: 0.9,
  ends,
});

// Back-row lugs point at the coils; front-row lugs point into the gap
// beside their stud, clear of the delta links.
const BACK_DIR = [0, -1];
const LEADS = PHASES.flatMap((_, i) => [
  leadPaths(i, -1, tongueEnd(FRONT[i], LEAD_DIR)),
  leadPaths(i, 1, tongueEnd(backOf(i), BACK_DIR)),
]);
const leadFloors = () => LEADS.map(({ floor }) => wire(floor, "from")).join("");
const leadTops = () => LEADS.map(({ top }) => wire(top, "to")).join("");

// Closed loop: each coil's two leads meet in one butt splice on its pad.
function splice(i) {
  const cx = COIL_X[i];
  const y = COIL_Y + 22;
  const sleeve = { x: cx - 4.5, y: y - 1.5, w: 9, d: 3, r: 1.4 };
  return [
    ...[-1, 1].map((side) => {
      const [ex, ey, ez] = exitOf(i, side);
      return wire([[ex, ey, ez + 0.8], [ex, ey + 4.4, PAD_Z], [ex, y, PAD_Z], [cx + side * 4.5, y, PAD_Z]], "from");
    }),
    S(k.slabOf(sleeve, 3, 2.6, P, 4, 0.3), { tone: "hi", lit: true }),
    L(k.sideSeam(sleeve, 4.3, P, 4), { tone: "lo" }),
  ].join("");
}

// Supply cables: from the glands at the front edge onto the front-row lugs.
function glands() {
  const out = [];
  const bar = { x: -48, y: GLAND_Y - 6, w: 96, d: 12, r: 2 };
  out.push(S(k.slabOf(bar, 0, 3, P, 4, 0.5), { tone: "mid" }));
  out.push(D([at([bar.x + 4, GLAND_Y, 3]), at([bar.x + bar.w - 4, GLAND_Y, 3])], { size: 0.5 }));
  for (const x of COL) {
    out.push(S(k.cylinder(x, GLAND_Y, 5, 3, 2.4, P, 6, 0.3), { tone: "mid" }));
    out.push(S(k.cylinder(x, GLAND_Y, 4, 5.4, 2.6, P, 28), { tone: "mid", inner: L(k.knurl(x, GLAND_Y, 4, 5.4, 8, 22, P), { tone: "lo" }) }));
    out.push(S(k.cylinder(x, GLAND_Y, 2.4, 8, 1.2, P, 20), { tone: "lo" }));
  }
  return out.join("");
}

function supply() {
  return FRONT.map(([x, y]) => {
    const end = tongueEnd([x, y], SUPPLY_DIR);
    const from = [x, GLAND_Y, 9.2];
    const via = [[x, GLAND_Y - 4, 15], [x, end[1] + 6, 14]].map(at);
    return k.wireSvg(at(from), at(end), { via, tone: "lit", size: 0.9 })
      + L(k.pathOf([at(from), ...via, at(end)]), { tone: "lit", flow: true, className: "wc-current" });
  }).join("");
}

// --- Assembly ---------------------------------------------------------------
const frontLugs = () => FRONT.map((p) => lug(p, LEAD_DIR)).join("");
const backLugs = () => PHASES.map((_, i) => lug(backOf(i), BACK_DIR)).join("");
const supplyLugs = () => FRONT.map((p) => lug(p, SUPPLY_DIR, LUG_Z - 0.01)).join("");
const nutsAt = (row) => STUDS.filter(([, y]) => y === row).map(nut).join("");

const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "A terminal box. Coils A, B and C are wired to six studs, and brass links on the studs set how the coils join.",
  body: [
    plate(),
    glands(),
    COIL_X.map((_, i) => coil(i) + eyelets(i)).join(""),
    show("closed", PHASES.map((_, i) => splice(i)).join("")),
    show("delta star", leadFloors()),
    block(),
    show("delta star", leadTops()),
    washers(),
    show("delta star", backLugs() + frontLugs() + supplyLugs()),
    show("delta", deltaLinks()),
    show("star", starBar()),
    nutsAt(ROW_BACK),
    show("delta star", supply()),
    nutsAt(ROW_FRONT),
  ],
});

export const MODE_CSS = `
.wc [data-show]{opacity:0;transition:opacity .5s var(--anatomy-ease)}
.wc[data-mode="closed"] [data-show~="closed"],.wc[data-mode="delta"] [data-show~="delta"],.wc[data-mode="star"] [data-show~="star"]{opacity:1}
@media (prefers-reduced-motion:reduce){.wc [data-show]{transition:none}}
`;

mkdirSync(ASSETS, { recursive: true });
writeFileSync(join(ASSETS, "winding-connection.svg"), svg + "\n");
writeFileSync(join(ASSETS, "iso.css"), `/* Generated by scripts/figures/winding-connection.mjs from the anatomy kit. */\n${k.ISO_CSS.trim()}\n${MODE_CSS.trim()}\n`);
console.log("wrote src/lib/assets/winding-connection.svg and iso.css");

if (process.argv.includes("--preview")) {
  const dir = "/tmp/winding-connection";
  mkdirSync(dir, { recursive: true });
  for (const theme of ["dark", "light"]) {
    for (const mode of ["closed", "delta", "star"]) {
      const body = k.plateHtml({
        fig: "Fig 1",
        title: "Winding connection",
        hint: mode,
        readout: mode,
        body: `<div class="wc" data-mode="${mode}">${svg}</div>`,
      });
      writeFileSync(join(dir, `${mode}-${theme}.html`), k.pageHtml({ title: mode, theme, body: `<style>${MODE_CSS}</style>${body}` }));
    }
  }
  console.log("wrote previews to", dir);
}
