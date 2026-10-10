import type { CadPoint, CadRouteCurve, CadRouteSpline } from "./types/dxf";

/** A true circular SVG arc through start, mid and end, not a quadratic fit. */
export function arcSvgPath({ start: a, mid: b, end: c }: CadRouteCurve): string {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(d) < 1e-12) return `M ${a.x} ${a.y} L ${c.x} ${c.y}`;
  const aa = a.x * a.x + a.y * a.y;
  const bb = b.x * b.x + b.y * b.y;
  const cc = c.x * c.x + c.y * c.y;
  const x = (aa * (b.y - c.y) + bb * (c.y - a.y) + cc * (a.y - b.y)) / d;
  const y = (aa * (c.x - b.x) + bb * (a.x - c.x) + cc * (b.x - a.x)) / d;
  const radius = Math.hypot(a.x - x, a.y - y);
  const tau = 2 * Math.PI;
  const angle = (p: CadPoint) => Math.atan2(p.y - y, p.x - x);
  const ccw = (angle(c) - angle(a) + tau) % tau;
  const throughMid = (angle(b) - angle(a) + tau) % tau;
  const positive = throughMid < ccw;
  const sweep = positive ? ccw : tau - ccw;
  return `M ${a.x} ${a.y} A ${radius} ${radius} 0 ${sweep > Math.PI ? 1 : 0} ${positive ? 1 : 0} ${c.x} ${c.y}`;
}

export function splinePointAt(spline: CadRouteSpline, t: number): CadPoint {
  const { degree: p, knots: k, control_points: points } = spline;
  const n = points.length;
  t = Math.max(k[p], Math.min(k[n], t));
  let span = n - 1;
  if (t < k[n]) {
    for (let i = p; i < n; i++) { if (t < k[i + 1]) { span = i; break; } }
  }
  const d = points.slice(span - p, span + 1).map((point, j) => {
    const w = spline.weights?.[span - p + j] ?? 1;
    return [point.x * w, point.y * w, w];
  });
  for (let r = 1; r <= p; r++) {
    for (let j = p; j >= r; j--) {
      const i = span - p + j;
      const denominator = k[i + p + 1 - r] - k[i];
      const a = denominator === 0 ? 0 : (t - k[i]) / denominator;
      for (let axis = 0; axis < 3; axis++) d[j][axis] = (1 - a) * d[j - 1][axis] + a * d[j][axis];
    }
  }
  return { x: d[p][0] / d[p][2], y: d[p][1] / d[p][2] };
}

/** Display/physics fallback for non-Bezier imported splines, never saved geometry. */
export function sampleSpline(spline: CadRouteSpline, stepsPerSpan = 16): CadPoint[] {
  const { degree: p, knots: k, control_points: points } = spline;
  const result = [splinePointAt(spline, k[p])];
  for (let i = p; i < points.length; i++) {
    if (k[i] === k[i + 1]) continue;
    for (let j = 1; j <= stepsPerSpan; j++) result.push(splinePointAt(spline, k[i] + (k[i + 1] - k[i]) * j / stepsPerSpan));
  }
  return result;
}

/** Generated splines are piecewise cubic Beziers stored as a single B-spline. */
export function splineSvgPath(spline: CadRouteSpline): string {
  const { degree: p, knots: k, control_points: points } = spline;
  const cubic = p === 3 && points.length % 3 === 1 && !spline.weights?.length
    && k.slice(0, 4).every((v) => v === k[0])
    && k.slice(-4).every((v) => v === k[k.length - 1])
    && k.slice(4, -4).every((v, i, values) => v === values[Math.floor(i / 3) * 3]);
  if (cubic) {
    let path = `M ${points[0].x} ${points[0].y}`;
    for (let i = 1; i < points.length; i += 3) {
      path += ` C ${points[i].x} ${points[i].y} ${points[i + 1].x} ${points[i + 1].y} ${points[i + 2].x} ${points[i + 2].y}`;
    }
    return path;
  }
  return sampleSpline(spline).map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ");
}
