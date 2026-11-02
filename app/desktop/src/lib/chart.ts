/** SVG chart scales, padded ranges, ticks and polylines. */

type LinearScale = (value: number) => number;

/**
 * Build a linear data→pixel scaler.
 *
 * @param min data value at `startPx`
 * @param max data value at `startPx + spanPx`
 * @param startPx pixel position of `min`
 * @param spanPx pixel length of the axis
 */
export function createLinearScale(
  min: number,
  max: number,
  startPx: number,
  spanPx: number,
): LinearScale {
  const denom = max - min || 1;
  const scale = spanPx / denom;
  return (value) => startPx + (value - min) * scale;
}

/** Pad a [min, max] range by `padFraction` of its width (0.08 ≈ 8%). */
export function paddedRange(
  values: number[],
  padFraction = 0.08,
): [number, number] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * padFraction || 0.001;
  return [min - pad, max + pad];
}

/** Evenly spaced tick values + pixel positions along a scale. */
export function ticks(
  min: number,
  max: number,
  count: number,
  sx: LinearScale,
): { v: number; pos: number }[] {
  return Array.from({ length: count }, (_, i) => {
    const v = min + ((max - min) * i) / (count - 1);
    return { v, pos: sx(v) };
  });
}

/** Render (xs, ys) pairs as an SVG polyline points string. */
export function polyline(sx: LinearScale, sy: LinearScale, xs: number[], ys: number[]): string {
  return ys.map((y, i) => `${sx(xs[i]).toFixed(1)},${sy(y).toFixed(1)}`).join(" ");
}
