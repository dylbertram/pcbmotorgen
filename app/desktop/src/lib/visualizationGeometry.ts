import { BufferGeometry, Color, Float32BufferAttribute, Vector3 } from "three";
import type { CadGeometry } from "./types";
import type { CoilScene } from "./coilScene";
import type { CopperLossPreview, FieldPreview } from "./types/simulationVisualization";

export const HEAT_PALETTE = ["#343c73", "#705680", "#aa6877", "#da8d60", "#f2c65c", "#fff1aa"];
export const FIELD_PALETTE = ["#225b91", "#2aa9b4", "#9fcfdb", "#e5d4f5"];
export function heatColor(value: number, maximum: number): string {
  return HEAT_PALETTE[Math.max(0, Math.min(HEAT_PALETTE.length - 1, Math.floor(maximum > 0 ? value / maximum * (HEAT_PALETTE.length - 1) : 0)))];
}

/** Physics metres, XYZ up, to the existing centered mm, Y-up scene. */
export function physicalToScene(positionM: number[], scene: Pick<CoilScene, "centerMm" | "scale">, zScale = 1): Vector3 {
  const p = new Vector3(positionM[0] * 1000, positionM[2] * 1000, -positionM[1] * 1000);
  p.sub(new Vector3(...scene.centerMm)).multiplyScalar(scene.scale);
  p.y *= zScale;
  return p;
}

// Ten-picometre keys absorb only SI/mm serialization roundoff, never feature
// spacing or a geometry-admission tolerance. Reordered primitives map by shape.
const coordinate = (x: number) => Math.round(x * 1e8);
const pointKey = (x: number, y: number) => `${coordinate(x)},${coordinate(y)}`;
function endsKey(a: { x: number; y: number }, b: { x: number; y: number }) {
  return [pointKey(a.x, a.y), pointKey(b.x, b.y)].sort().join("/");
}

/** Assign actual graph-edge W to the original display primitive, not a hot-spot interpolation. */
export function mapCopperLoss(geometry: CadGeometry, heat: CopperLossPreview): Map<string, number> {
  const result = new Map<string, number>();
  const lookup = new Map<string, string[]>();
  const phase = (net: string) => geometry.coil_phases?.[net] ?? net;
  const add = (key: string, value: string) => lookup.set(key, [...(lookup.get(key) ?? []), value]);
  geometry.routing.segments.forEach((s, i) => add(`trace:${phase(s.net)}:${s.layer}:${endsKey(s.start, s.end)}`, `segment-${i}`));
  geometry.routing.curves.forEach((s, i) => add(`arc:${phase(s.net)}:${s.layer}:${endsKey(s.start, s.end)}`, `arc-${i}`));
  for (const edge of heat.edges) {
    let matches: string[];
    if (edge.kind === "trace") {
      const a = edge.points_m[0], b = edge.points_m.at(-1)!;
      const kind = edge.points_m.length > 2 ? "arc" : "trace";
      const endpoints = endsKey({ x: a[0] * 1000, y: a[1] * 1000 }, { x: b[0] * 1000, y: b[1] * 1000 });
      matches = lookup.get(`${kind}:${edge.net}:${edge.layers[0]}:${endpoints}`) ?? [];
      if (matches.length === 1) {
        const z = geometry.layer_z_mm[edge.layers[0]] * .001;
        if (!Number.isFinite(z) || edge.points_m.some(p => Math.abs(p[2] - z) > 1e-12)) throw new Error("Loss data and viewer copper depths differ");
      }
    } else {
      const p = edge.points_m[0], low = Math.min(...edge.layers), high = Math.max(...edge.layers);
      matches = geometry.routing.vias.flatMap((v, i) => phase(v.net) === edge.net
        && pointKey(v.position.x, v.position.y) === pointKey(p[0] * 1000, p[1] * 1000)
        && Math.min(v.from_layer, v.to_layer) <= low && Math.max(v.from_layer, v.to_layer) >= high ? [`via-${i}`] : []);
      if (edge.points_m.some((p, i) => !Number.isFinite(geometry.layer_z_mm[edge.layers[i]])
        || Math.abs(p[2] - geometry.layer_z_mm[edge.layers[i]] * .001) > 1e-12)) throw new Error("Loss data and viewer barrel depths differ");
    }
    if (matches.length !== 1) throw new Error("Current loss cannot be assigned uniquely to the active copper. No fitted map is shown.");
    result.set(matches[0], (result.get(matches[0]) ?? 0) + edge.loss_w);
  }
  const total = [...result.values()].reduce((a, b) => a + b, 0);
  if (Math.abs(total - heat.total_loss_w) > Math.max(1e-12, total * 1e-8)) throw new Error("Viewer loss mapping does not conserve native copper power");
  return result;
}

/** Batched shafts and heads: one draw call, magnitude color in physical tesla. */
export function fieldGlyphGeometry(field: FieldPreview, scene: CoilScene, zScale: number): BufferGeometry {
  const positions: number[] = [], colors: number[] = [];
  const maximum = Math.max(0, ...field.samples.map(v => v.magnitude_t));
  const length = .32;
  const segment = (a: Vector3, b: Vector3, color: Color) => {
    positions.push(...a.toArray(), ...b.toArray());colors.push(...color.toArray(), ...color.toArray());
  };
  for (const sample of field.samples) {
    if (sample.magnitude_t === 0) continue;
    const fraction = maximum > 0 ? sample.magnitude_t / maximum : 0;
    const color = new Color(FIELD_PALETTE[Math.min(FIELD_PALETTE.length - 1, Math.floor(fraction * (FIELD_PALETTE.length - 1)))]);
    const start = physicalToScene(sample.position_m, scene, zScale);
    const direction = new Vector3(sample.b_t[0], sample.b_t[2] * zScale, -sample.b_t[1]).normalize();
    const end = start.clone().addScaledVector(direction, length * (.2 + .8 * fraction));
    const side = direction.clone().cross(Math.abs(direction.y) > .9 ? new Vector3(1, 0, 0) : new Vector3(0, 1, 0)).normalize();
    const head = end.clone().addScaledVector(direction, -length * .23);
    segment(start, end, color);segment(end, head.clone().addScaledVector(side, length * .1), color);segment(end, head.clone().addScaledVector(side, -length * .1), color);
  }
  return new BufferGeometry().setAttribute("position", new Float32BufferAttribute(positions, 3)).setAttribute("color", new Float32BufferAttribute(colors, 3));
}
