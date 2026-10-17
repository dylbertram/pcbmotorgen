import type { CadGeometry, LinearMotorConfig } from "./types";
import { coilNames, phaseOf, PHASE_LABELS } from "./cadPhases";
import { splinePointAt } from "./curvePaths";
import { coilsMissingEnds } from "./cadTerminals";

/** Early UI checks. The backend repeats these before every motor workflow. */
export function cadMappingProblems(g: CadGeometry, phases: number, minimumWidth: number): string[] {
  const problems: string[] = [];
  if (!g.motor_mapping_reviewed) problems.push("Review conductor roles, layer heights, and via connections.");
  if (!Number.isFinite(g.trace_width_mm) || g.trace_width_mm < minimumWidth || g.trace_width_mm <= 0)
    problems.push(`Imported trace width must be at least ${minimumWidth} mm.`);
  if (!g.layer_z_mm.length || !g.layer_z_mm.every(Number.isFinite)) problems.push("Set finite copper layer heights.");
  const labels = PHASE_LABELS.slice(0, phases);
  const coils = coilNames(g);
  const missingEnds = new Set(coilsMissingEnds(g));
  if (!coils.length) problems.push("Imported geometry has no copper.");
  for (const coil of coils) {
    if (!labels.includes(phaseOf(g, coil) ?? "")) problems.push(`Assign a configured motor phase to coil '${coil}'.`);
    if (!g.coil_terminals?.[coil] || missingEnds.has(coil)) problems.push(`Select driver and opposite ends for coil '${coil}'.`);
  }
  for (const label of labels) {
    if (!coils.some((coil) => phaseOf(g, coil) === label)) problems.push(`No imported coil is assigned to phase ${label}.`);
  }
  const endpoints = [
    ...g.routing.segments.map((s) => ({ ...s, points: [s.start, s.end] })),
    ...g.routing.curves.map((s) => ({ ...s, points: [s.start, s.end] })),
    ...(g.routing.splines ?? []).map((s) => ({ ...s, points: [splinePointAt(s, s.knots[s.degree]), splinePointAt(s, s.knots[s.control_points.length])] })),
  ];
  for (const s of endpoints) {
    if (!Number.isInteger(s.layer) || s.layer < 0 || s.layer >= g.layer_z_mm.length)
      problems.push(`Coil '${s.net}' refers to missing layer ${s.layer}.`);
  }
  g.routing.vias.forEach((v, i) => {
    if (v.from_layer === v.to_layer) problems.push(`Via ${i + 1} must connect distinct copper layers.`);
    for (const layer of [v.from_layer, v.to_layer]) {
      if (!endpoints.some((s) => s.net === v.net && s.layer === layer && s.points.some((p) => Math.hypot(p.x - v.position.x, p.y - v.position.y) <= 1e-6)))
        problems.push(`Via ${i + 1} on coil '${v.net}' has no trace endpoint on layer ${layer}.`);
    }
  });
  return [...new Set(problems)];
}

export function assertCadMapping(g: CadGeometry | null, config: LinearMotorConfig): void {
  if (!g) return;
  const problems = cadMappingProblems(g, config.phases, config.min_trace_m * 1000);
  if (problems.length) throw new Error(problems.join(" "));
}
