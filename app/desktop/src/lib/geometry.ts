/**
 * Pure geometry helpers shared by the SVG visualization components.
 *
 * All functions are deterministic and unit-agnostic (callers pick mm or m
 * consistently). Extracted from TravelDiagram / FluxDiagram / CoilPreview /
 * DesignDimensions to remove duplicated derived math.
 */

/** Phase-band pitch: vernier fraction of the pole pitch per phase. */
export function phaseBandPitchMm(
  polePitchMm: number,
  phases: number,
  spacingRatio: number,
): number {
  return (polePitchMm / phases) * spacingRatio;
}

/**
 * Vernier rest offset: the unresolvable remainder of the phase-band pitch —
 * `(τp/phases)(1 − ratio)` is the slice of one phase-band pitch the reduced
 * vernier ratio leaves unvisited, so rest positions drift by this much per
 * phase band instead of realigning every pole pitch.
 */
export function restOffsetMm(
  polePitchMm: number,
  phases: number,
  spacingRatio: number,
): number {
  return Math.max(0, (polePitchMm / phases) * (1 - spacingRatio));
}

// ---------------------------------------------------------------------------
// Axonometric (3/4 isometric) projection — TravelDiagram iso view
// ---------------------------------------------------------------------------

/**
 * Vertical exaggeration factor of the 3/4 iso view: the PCB stackup
 * (1.6 mm board, 0.5 mm gap…) is invisible at true scale next to a
 * ~200 mm travel axis, so Z is drawn ×10. Single-sourced here — the iso
 * view projects with it and the reflection's hint text quotes it.
 */
export const ISO_Z_EXAG = 10;

/**
 * Axonometric projection shared by the iso view's wireframes:
 *     sx = cx + (x + 0.45·y) · sxy
 *     sy = cy + (−z·sz + 0.45·y·sxy)
 * The 0.45 Y-coupling gives a ~24° "3/4" look from above-front.
 */
export function isoProject(
  x: number,
  y: number,
  z: number,
  cx: number,
  cy: number,
  sxy: number,
  sz: number,
): [number, number] {
  return [cx + (x + 0.45 * y) * sxy, cy + (-z * sz + 0.45 * y * sxy)];
}

/**
 * Center an assembly's bounding box inside the iso canvas. Projects the
 * 8 corners of the Z-stack bounding box, then returns the screen offset
 * that centers the hull.
 */
export function isoCenter(
  dims: { length: number; width: number; totalHeight: number },
  canvasW: number,
  canvasH: number,
  project: (x: number, y: number, z: number, cx: number, cy: number) => [number, number],
): { cx: number; cy: number } {
  const { length: L, width: W, totalHeight: H } = dims;
  const corners: [number, number, number][] = [
    [0, 0, 0], [L, 0, 0], [L, W, 0], [0, W, 0],
    [0, 0, H], [L, 0, H], [L, W, H], [0, W, H],
  ];
  let minSx = Infinity,
    minSy = Infinity,
    maxSx = -Infinity,
    maxSy = -Infinity;
  const tmpCx = canvasW / 2;
  const tmpCy = canvasH / 2;
  for (const [x, y, z] of corners) {
    const [sx, sy] = project(x, y, z, tmpCx, tmpCy);
    minSx = Math.min(minSx, sx);
    minSy = Math.min(minSy, sy);
    maxSx = Math.max(maxSx, sx);
    maxSy = Math.max(maxSy, sy);
  }
  return {
    cx: canvasW / 2 + (tmpCx - (minSx + maxSx) / 2),
    cy: canvasH / 2 + (tmpCy - (minSy + maxSy) / 2),
  };
}

/**
 * Render a 3D box as a wireframe SVG path string + projected corners.
 * Returns `d` (the `d` attribute) and `corners` (8 projected points).
 */
export function isoBoxPath(
  x0: number,
  y0: number,
  z0: number,
  dx: number,
  dy: number,
  dz: number,
  cx: number,
  cy: number,
  project: (x: number, y: number, z: number, cx: number, cy: number) => [number, number],
): { d: string; corners: [number, number][] } {
  const x1 = x0 + dx, y1 = y0 + dy, z1 = z0 + dz;
  const pts: [number, number, number][] = [
    [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], // bottom
    [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], // top
  ];
  const s = pts.map(([x, y, z]) => project(x, y, z, cx, cy));
  const edges: [number, number][][] = [
    // bottom rectangle
    [s[0], s[1]], [s[1], s[2]], [s[2], s[3]], [s[3], s[0]],
    // top rectangle
    [s[4], s[5]], [s[5], s[6]], [s[6], s[7]], [s[7], s[4]],
    // verticals
    [s[0], s[4]], [s[1], s[5]], [s[2], s[6]], [s[3], s[7]],
  ];
  const d = edges
    .map(([a, b]) => `M ${a[0].toFixed(1)} ${a[1].toFixed(1)} L ${b[0].toFixed(1)} ${b[1].toFixed(1)}`)
    .join(" ");
  return { d, corners: s };
}