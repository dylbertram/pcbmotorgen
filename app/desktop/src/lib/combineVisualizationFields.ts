import type { FieldPreview } from "./types/simulationVisualization";

/** Free-space vector superposition only. Never sum magnitudes or interpolate
 * between different observation grids. This is not a coupled material solve. */
export function combineVisualizationFields(coil: FieldPreview, pm: FieldPreview): FieldPreview {
  if (coil.method !== "qualified-finite-copper-winding-xyz" || pm.method !== "analytical-pm-only-xyz"
    || coil.samples.length !== pm.samples.length) throw new Error("Matching native coil and PM observations required");
  const samples = coil.samples.map((sample, i) => {
    const other = pm.samples[i];
    if (sample.position_m.length !== 3 || other.position_m.length !== 3
      || sample.position_m.some((v, axis) => !Number.isFinite(v) || !Number.isFinite(other.position_m[axis]) || Math.abs(v - other.position_m[axis]) > 1e-12)) throw new Error("Coil and PM observation grids differ");
    const b = sample.b_t.map((v, axis) => v + other.b_t[axis]) as [number, number, number];
    if (!b.every(Number.isFinite)) throw new Error("Nonfinite combined field");
    return { position_m: [...sample.position_m] as [number, number, number], b_t: b, magnitude_t: Math.hypot(...b) };
  });
  return { method: "coil-plus-pm-free-space-superposition", scope: "Audited DC coil source plus analytical permanent magnets in free space. No magnetic-material reaction or coupled-field qualification.", samples, magnets: pm.magnets };
}
