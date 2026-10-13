import type { CadCoilTerminals, CadGeometry, CadTerminal } from "./types";
import { splinePointAt } from "./curvePaths";

export function sameTerminal(a: CadTerminal, b: CadTerminal): boolean {
  return a.layer === b.layer && Math.hypot(a.position.x - b.position.x, a.position.y - b.position.y) <= 1e-9;
}

/** Original trace endpoints only. No snapping, via centres or spline controls. */
export function cadTerminalCandidates(geometry: CadGeometry, coil: string): CadTerminal[] {
  const points: CadTerminal[] = [];
  const add = (point: CadTerminal) => {
    if (!points.some((p) => sameTerminal(p, point))) points.push(point);
  };
  for (const trace of [...geometry.routing.segments, ...geometry.routing.curves]) {
    if (trace.net !== coil) continue;
    add({ position: trace.start, layer: trace.layer });
    add({ position: trace.end, layer: trace.layer });
  }
  for (const spline of geometry.routing.splines ?? []) {
    if (spline.net !== coil) continue;
    add({ position: splinePointAt(spline, spline.knots[spline.degree]), layer: spline.layer });
    add({ position: splinePointAt(spline, spline.knots[spline.control_points.length]), layer: spline.layer });
  }
  return points.sort((a, b) => a.layer - b.layer || a.position.x - b.position.x || a.position.y - b.position.y);
}

export function assignCadTerminals(geometry: CadGeometry, coil: string, terminals: CadCoilTerminals): CadGeometry {
  const candidates = cadTerminalCandidates(geometry, coil);
  if (!candidates.some((p) => sameTerminal(p, terminals.input)) || !candidates.some((p) => sameTerminal(p, terminals.output))) {
    throw new Error("Choose trace endpoints belonging to this coil.");
  }
  if (sameTerminal(terminals.input, terminals.output)) throw new Error("IN and OUT must be different endpoints.");
  const copy = (terminal: CadTerminal): CadTerminal => ({ position: { ...terminal.position }, layer: terminal.layer });
  return { ...geometry, coil_terminals: { ...geometry.coil_terminals, [coil]: { input: copy(terminals.input), output: copy(terminals.output) } } };
}

export function terminalDescription(terminal: CadTerminal): string {
  return `L${terminal.layer}, X ${Number(terminal.position.x.toFixed(6))} mm, Y ${Number(terminal.position.y.toFixed(6))} mm`;
}
