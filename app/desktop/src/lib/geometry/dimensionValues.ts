/** True when a dimension is finite and strictly positive. */
export function isPositiveFiniteDimension(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}
