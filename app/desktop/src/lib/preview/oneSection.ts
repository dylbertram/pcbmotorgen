import type { CoilArcDto, CoilPathDto, CoilSegmentDto, PhaseCoilDto } from "../types";

function selectedActiveConductorIndices(phase: PhaseCoilDto, count: number): Set<number> {
  const indices = new Set<number>();
  const firstIndex = new Map<CoilSegmentDto, number>();
  let activeCount = 0;
  for (let index = 0; index < phase.segments.length && activeCount < count; index++) {
    const segment = phase.segments[index];
    if (!segment.is_active) continue;
    if (!firstIndex.has(segment)) firstIndex.set(segment, index);
    indices.add(firstIndex.get(segment)!);
    activeCount++;
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
  const visible = new Map<number, CoilSegmentDto[]>();
  if (!oneSection) {
    for (const phase of coils.phases) {
      visible.set(phase.phase_idx * 1000 + phase.layer_idx, phase.segments);
    }
    return visible;
  }
  for (const phase of coils.phases) {
    const key = phase.phase_idx * 1000 + phase.layer_idx;
    const selected = selectedActiveConductorIndices(phase, oneSectionConductorCount);
    let firstSelected = Infinity, lastSelected = -Infinity;
    for (const index of selected) {
      firstSelected = Math.min(firstSelected, index);
      lastSelected = Math.max(lastSelected, index);
    }
    const segments: CoilSegmentDto[] = [];
    for (let i = 0; i < phase.segments.length; i++) {
      if (phase.segments[i].is_active) {
        if (selected.has(i)) segments.push(phase.segments[i]);
      } else {
        // Keep end-turns between the selected conductors only.
        if (i > firstSelected && i < lastSelected) segments.push(phase.segments[i]);
      }
    }
    visible.set(key, segments);
  }
  return visible;
}

/** Filter arcs using the x range of the same selected conductors. */
export function computeVisibleArcs(
  coils: CoilPathDto | null,
  oneSection: boolean,
  oneSectionConductorCount: number,
): Map<number, CoilArcDto[]> {
  if (!coils) return new Map();
  const visible = new Map<number, CoilArcDto[]>();
  if (!oneSection) {
    for (const phase of coils.phases) {
      visible.set(phase.phase_idx * 1000 + phase.layer_idx, phase.corner_arcs ?? []);
    }
    return visible;
  }
  for (const phase of coils.phases) {
    const key = phase.phase_idx * 1000 + phase.layer_idx;
    const arcs: CoilArcDto[] = [];
    const selected = selectedActiveConductorIndices(phase, oneSectionConductorCount);
    if (selected.size > 0) {
      let minX = Infinity, maxX = -Infinity;
      for (const i of selected) {
        const segment = phase.segments[i];
        minX = Math.min(minX, segment.start[0], segment.end[0]);
        maxX = Math.max(maxX, segment.start[0], segment.end[0]);
      }
      for (const arc of phase.corner_arcs ?? []) {
        if ((arc.start[0] >= minX && arc.start[0] <= maxX) || (arc.end[0] >= minX && arc.end[0] <= maxX)) {
          arcs.push(arc);
        }
      }
    }
    visible.set(key, arcs);
  }
  return visible;
}
