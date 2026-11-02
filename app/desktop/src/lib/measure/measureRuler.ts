import type { ViewportBBox, WorldTransform } from "../chart";

/** A point in virtual pixels or world metres, depending on the caller. */
export interface Point2D { x: number; y: number }

/** Convert client coordinates to the preview's virtual drawing space. */
export function clientToVirtual(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
  virtualW: number,
  virtualH: number,
): Point2D {
  return {
    x: rect.width > 0 ? ((clientX - rect.left) / rect.width) * virtualW : 0,
    y: rect.height > 0 ? ((clientY - rect.top) / rect.height) * virtualH : 0,
  };
}

/** Invert the preview's world-to-virtual transform, including pan. */
export function virtualToWorld(
  vx: number,
  vy: number,
  t: WorldTransform,
  panX: number,
  panY: number,
): Point2D {
  if (t.s <= 0) return { x: 0, y: 0 };
  return { x: (vx - (t.tx + panX)) / t.s, y: (t.ty + panY - vy) / t.s };
}

export interface MeasureRuler {
  p1: Point2D;
  p2: Point2D;
  mm: number;
  label: Point2D;
  bounds: ViewportBBox;
}

/** Build a world-space ruler with a perpendicular caption offset. */
export function computeMeasureRuler(p1: Point2D, p2: Point2D): MeasureRuler {
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  const len = Math.hypot(dx, dy);
  const nx = len > 0 ? -dy / len : 1;
  const ny = len > 0 ? dx / len : 0;
  const labelRaiseM = 0.0012;
  const padXM = Math.max(len * 0.05, 0.001);
  return {
    p1,
    p2,
    mm: len * 1000,
    label: {
      x: (p1.x + p2.x) / 2 + nx * labelRaiseM,
      y: (p1.y + p2.y) / 2 + ny * labelRaiseM,
    },
    bounds: {
      minX: Math.min(p1.x, p2.x) - padXM,
      minY: Math.min(p1.y, p2.y) - 0.004,
      maxX: Math.max(p1.x, p2.x) + padXM,
      maxY: Math.max(p1.y, p2.y) + 0.004,
    },
  };
}
