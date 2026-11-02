export interface ViewportBBox {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** Union of several world-space boxes into one. */
export function unionBounds(...boxes: ViewportBBox[]): ViewportBBox {
  if (boxes.length === 0) return { minX: 0, minY: 0, maxX: 0.001, maxY: 0.001 };
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const b of boxes) {
    minX = Math.min(minX, b.minX); minY = Math.min(minY, b.minY);
    maxX = Math.max(maxX, b.maxX); maxY = Math.max(maxY, b.maxY);
  }
  return { minX, minY, maxX: Math.max(maxX, minX + 1e-6), maxY: Math.max(maxY, minY + 1e-6) };
}

export interface WorldTransform {
  s: number;
  tx: number;
  ty: number;
}

/**
 * Fit a world bbox into `viewW × viewH` minus `pad` on each side, with
 * `meet` aspect behaviour (smaller of the two scales, bbox never
 * overflows) and optional zoom. The returned transform assumes the group
 * applies `scale(1, −1)` before the translate, so y-up world coordinates
 * render correctly in SVG's y-down screen space:
 *   `transform="translate(tx, ty) scale(1 -1) scale(s)"` with world
 *   coordinates drawn directly; the returned translation accounts for bbox.
 */
export function fitWorldToView(
  bbox: ViewportBBox,
  viewW: number,
  viewH: number,
  pad: number,
  zoom = 1,
): WorldTransform {
  const bboxW = bbox.maxX - bbox.minX;
  const bboxH = bbox.maxY - bbox.minY;
  const drawW = viewW - 2 * pad;
  const drawH = viewH - 2 * pad;
  const fitScale = Math.min(drawW / bboxW, drawH / bboxH);
  const s = fitScale * zoom;
  const renderedW = bboxW * s;
  const renderedH = bboxH * s;
  const cx = pad + (drawW - renderedW) / 2;
  const cy = pad + (drawH - renderedH) / 2;
  return {
    s,
    // After scale(1, -1) the y-axis is flipped; ty shifts so the
    // bbox top (world maxY) lands at `cy` and the bbox bottom
    // (world minY) lands at `cy + bboxH*s`.
    tx: cx - bbox.minX * s,
    ty: cy + bbox.maxY * s,
  };
}
