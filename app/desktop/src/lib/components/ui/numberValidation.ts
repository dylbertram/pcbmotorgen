/**
 * Epsilon-tolerant multiple check matching the routing crate's 1e-9 tolerance.
 * Non-finite values and invalid multiples pass; the backend owns rejection.
 */
export function isMultipleOf(value: number, multipleOf: number): boolean {
  if (!Number.isFinite(value)) return true;
  if (!Number.isFinite(multipleOf) || multipleOf <= 0) return true;
  const scaled = value / multipleOf;
  return Math.abs(Math.round(scaled) - scaled) * multipleOf <= 1e-9;
}
