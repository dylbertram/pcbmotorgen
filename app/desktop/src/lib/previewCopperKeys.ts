import type { CadGeometry, CoilPathDto, CoilSegmentDto, CoilArcDto } from "./types";

/** Filter scene keys, never rebuild/reindex geometry used by native heat maps. */
export function previewCopperKeys(geometry: CadGeometry | null, coils: CoilPathDto | null,
  segments: ReadonlyMap<number,CoilSegmentDto[]>, arcs: ReadonlyMap<number,CoilArcDto[]>): Set<string> {
  const keys = new Set<string>();
  if (!geometry || !coils) return keys;
  const point = (x:number,y:number) => `${Math.round(x*1e6)},${Math.round(y*1e6)}`;
  const lineKey = (a:string,b:string) => [a,b].sort().join(":");
  const allowed = new Map<string, {lines:Set<string>;arcs:Set<string>; minX:number; maxX:number}>();
  for (const phase of coils.phases) {
    const visible = segments.get(phase.phase_idx*1000+phase.layer_idx) ?? phase.segments;
    const curves = arcs.get(phase.phase_idx*1000+phase.layer_idx) ?? phase.corner_arcs ?? [];
    const xs = visible.flatMap(s => [s.start[0]*1000,s.end[0]*1000]);
    allowed.set(`${phase.phase_name}:${phase.layer_idx}`,{
      lines:new Set(visible.map(s=>lineKey(point(s.start[0]*1000,s.start[1]*1000),point(s.end[0]*1000,s.end[1]*1000)))),
      arcs:new Set(curves.map(s=>`${lineKey(point(s.start[0]*1000,s.start[1]*1000),point(s.end[0]*1000,s.end[1]*1000))}:${point(s.mid[0]*1000,s.mid[1]*1000)}`)),
      minX:Math.min(...xs),maxX:Math.max(...xs),
    });
  }
  geometry.routing.segments.forEach((s,i)=>{if(allowed.get(`${s.net}:${s.layer}`)?.lines.has(lineKey(point(s.start.x,s.start.y),point(s.end.x,s.end.y))))keys.add(`segment-${i}`);});
  geometry.routing.curves.forEach((s,i)=>{if(allowed.get(`${s.net}:${s.layer}`)?.arcs.has(`${lineKey(point(s.start.x,s.start.y),point(s.end.x,s.end.y))}:${point(s.mid.x,s.mid.y)}`))keys.add(`arc-${i}`);});
  (geometry.routing.splines ?? []).forEach((s,i)=>{const a=allowed.get(`${s.net}:${s.layer}`);if(a && s.control_points.every(p=>p.x>=a.minX-1e-6&&p.x<=a.maxX+1e-6))keys.add(`spline-${i}`);});
  return keys;
}
