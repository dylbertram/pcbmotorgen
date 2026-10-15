/**
 * Holding-force profile math for the mover-position chart.
 *
 * Under a fixed balanced excitation (baseline IA=+I, IB=0, IC=−I) the thrust
 * on a coreless mover whose array spans whole electrical cycles is sinusoidal
 * in the displacement from its stable rest phase:
 *
 *   F(x) = −sin(2π(x − φ) / P_e)      (normalized to ±1)
 *
 * Zeros fall EXACTLY on every stable rest position x ≡ φ (mod P_e) and the
 * slope there is negative (restoring), matching the equilibrium envelope that
 * bounds the position slider. Pure functions, shared by the chart and tests.
 */

const TWO_PI = 2 * Math.PI;

/** Normalized holding force at position `xMm`. */
export function holdingForceAt(
  xMm: number,
  restPhaseMm: number,
  periodMm: number,
): number {
  if (!(periodMm > 0)) return 0;
  return -Math.sin((TWO_PI * (xMm - restPhaseMm)) / periodMm);
}

/**
 * Sample the profile across [minX, maxX] at `n` points (inclusive).
 * Guards degenerate ranges so the chart always gets finite data.
 */
export function sampleHoldingForce(
  minX: number,
  maxX: number,
  restPhaseMm: number,
  periodMm: number,
  n = 200,
): { xs: number[]; ys: number[] } {
  const count = Math.max(2, Math.floor(n));
  const lo = Number.isFinite(minX) ? minX : 0;
  const hi = Number.isFinite(maxX) && maxX > lo ? maxX : lo + 1;
  const xs: number[] = [];
  const ys: number[] = [];
  for (let i = 0; i < count; i++) {
    const x = lo + ((hi - lo) * i) / (count - 1);
    xs.push(x);
    ys.push(holdingForceAt(x, restPhaseMm, periodMm));
  }
  return { xs, ys };
}

/**
 * Stable rest positions x ≡ φ (mod period) inside [minX, maxX] (inclusive).
 * Returns [] for a non-positive period.
 */
export function restPositions(
  minX: number,
  maxX: number,
  restPhaseMm: number,
  periodMm: number,
): number[] {
  if (!(periodMm > 0) || !(maxX >= minX)) return [];
  // First rest position ≥ minX: k = ceil((minX − φ)/period)
  const k0 = Math.ceil((minX - restPhaseMm) / periodMm);
  const out: number[] = [];
  for (let k = k0; ; k++) {
    const x = restPhaseMm + k * periodMm;
    if (x > maxX) break;
    if (x >= minX) out.push(x);
  }
  return out;
}

/**
 * Per-phase holding force. Phase `p` carries currents shifted by p·(360°/N)
 * electrically, so its normalized wave is the baseline sinusoid spatially
 * offset by p·P_e/N — for a 3-phase motor three sine waves mutually offset
 * by 120° (P_e/3). The phase-A wave (p=0) is the combined-profile reference
 * whose zeros mark the stable rest positions.
 */
export function holdingForceAtPhase(
  xMm: number,
  phaseIdx: number,
  phaseCount: number,
  restPhaseMm: number,
  periodMm: number,
): number {
  const n = Math.max(1, Math.floor(phaseCount));
  const shift = phaseIdx * (periodMm / n);
  return holdingForceAt(xMm, restPhaseMm + shift, periodMm);
}

/** Stroke palette per phase (cycles if phases > colours). */
const PHASE_STROKES = [
  "stroke-emerald-400",
  "stroke-sky-400",
  "stroke-violet-400",
] as const;

/** Marker-dot fill per phase (matches PHASE_STROKES). */
const PHASE_FILLS = ["fill-emerald-300", "fill-sky-300", "fill-violet-300"] as const;

export function phaseStroke(phaseIdx: number): string {
  return PHASE_STROKES[phaseIdx % PHASE_STROKES.length];
}

export function phaseFill(phaseIdx: number): string {
  return PHASE_FILLS[phaseIdx % PHASE_FILLS.length];
}
