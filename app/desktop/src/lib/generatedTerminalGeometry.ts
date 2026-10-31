import type { CadGeometry, CoilPathDto } from "./types";
import { withAutomaticCadTerminals } from "./cadTerminals";

/** Generated preview coordinates are metres; terminal editing uses millimetres. */
export function generatedTerminalGeometry(coils: CoilPathDto, layerCount: number, thickness: number, traceWidth: number, connection?: number | "star" | "delta" | "closed"): CadGeometry {
  const point = ([x, y]: [number, number]) => ({ x: x * 1000, y: y * 1000 });
  const geometry: CadGeometry = {
    // Match DriveGeometryHints::layer_z and the actual generated host export:
    // layer0 is PCB top z=0; increasing layer indices run down into the board.
    layer_z_mm: Array.from({ length: layerCount }, (_, i) => i === 0 ? 0 : -thickness * i / (layerCount - 1)),
    trace_width_mm: traceWidth,
    ...(connection === 1 || connection === "delta" ? { terminal_connection: "delta" as const } : connection === 2 || connection === "star" ? { terminal_connection: "star" as const } : {}),
    routing: {
      format_version: 2,
      segments: coils.phases.flatMap((phase) => phase.segments.map((segment) => ({ ...segment, start: point(segment.start), end: point(segment.end), layer: phase.layer_idx, net: phase.phase_name }))),
      curves: coils.phases.flatMap((phase) => (phase.corner_arcs ?? []).map((arc) => ({ start: point(arc.start), mid: point(arc.mid), end: point(arc.end), is_active: arc.is_active ?? false, layer: phase.layer_idx, net: phase.phase_name }))),
      vias: coils.phases.flatMap((phase) => phase.routed_vias != null
        ? phase.routed_vias.map((via) => ({ ...via, position: point(via.position), net: phase.phase_name }))
        : (phase.via_positions ?? []).map((position) => ({ position: point(position), net: phase.phase_name, from_layer: phase.layer_idx % 2 === 0 ? phase.layer_idx : phase.layer_idx - 1, to_layer: phase.layer_idx % 2 === 0 ? phase.layer_idx + 1 : phase.layer_idx })))
        .filter((via) => via.from_layer >= 0 && via.to_layer >= 0 && via.from_layer < layerCount && via.to_layer < layerCount),
    },
  };
  // Both layer presentations can carry the same physical via.
  geometry.routing.vias = geometry.routing.vias.filter((via, index, all) => all.findIndex((other) => JSON.stringify(other) === JSON.stringify(via)) === index);
  return withAutomaticCadTerminals(geometry);
}
