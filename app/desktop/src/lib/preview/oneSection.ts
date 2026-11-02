import type { CoilArcDto, CoilPathDto, CoilSegmentDto, PhaseCoilDto } from "../types";

function selectedActiveConductorIndices(phase: PhaseCoilDto, count: number): Set<number> {
  const active = phase.segments.filter((segment) => segment.is_active);
  const indices = new Set<number>();
  for (let i = 0; i < Math.min(count, active.length); i++) {
    indices.add(phase.segments.indexOf(active[i]));
  }
  return indices;
}

/** Filter to the first N active conductors and their interior end-turns. */
export function computeVisibleSegments(
  coils: CoilPathDto | null,
  oneSection: boolean,
  oneSectionConductorCount: number,
): Map<number, CoilSegmentDto[]> {
  if (!coils) return new Map();
  const m = new Map<number, CoilSegmentDto[]>();
  if (!oneSection) {
    for (const ph of coils.phases) {
      m.set(ph.phase_idx * 1000 + ph.layer_idx, ph.segments);
    }
    return m;
  }
  for (const ph of coils.phases) {
    const key = ph.phase_idx * 1000 + ph.layer_idx;
    const keepIdx = selectedActiveConductorIndices(ph, oneSectionConductorCount);
    const keptSegs: CoilSegmentDto[] = [];
    for (let i = 0; i < ph.segments.length; i++) {
      if (ph.segments[i].is_active) {
        if (keepIdx.has(i)) keptSegs.push(ph.segments[i]);
      } else {
        // Keep end-turns between the selected conductors only.
        const firstKept = Math.min(...keepIdx);
        const lastKept = Math.max(...keepIdx);
        if (i > firstKept && i < lastKept) keptSegs.push(ph.segments[i]);
      }
    }
    m.set(key, keptSegs);
  }
  return m;
}

/** Filter arcs using the x range of the same selected conductors. */
export function computeVisibleArcs(
  coils: CoilPathDto | null,
  oneSection: boolean,
  oneSectionConductorCount: number,
): Map<number, CoilArcDto[]> {
  if (!coils) return new Map();
  const m = new Map<number, CoilArcDto[]>();
  if (!oneSection) {
    for (const ph of coils.phases) {
      m.set(ph.phase_idx * 1000 + ph.layer_idx, ph.corner_arcs ?? []);
    }
    return m;
  }
  for (const ph of coils.phases) {
    const key = ph.phase_idx * 1000 + ph.layer_idx;
    const keptArcs: CoilArcDto[] = [];
    const keepIdx = selectedActiveConductorIndices(ph, oneSectionConductorCount);
    if (keepIdx.size > 0) {
      let minX = Infinity, maxX = -Infinity;
      for (const i of keepIdx) {
        const s = ph.segments[i];
        minX = Math.min(minX, s.start[0], s.end[0]);
        maxX = Math.max(maxX, s.start[0], s.end[0]);
      }
      for (const a of ph.corner_arcs ?? []) {
        if ((a.start[0] >= minX && a.start[0] <= maxX) || (a.end[0] >= minX && a.end[0] <= maxX)) {
          keptArcs.push(a);
        }
      }
    }
    m.set(key, keptArcs);
  }
  return m;
}
