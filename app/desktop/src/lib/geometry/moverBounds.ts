/** Bounds of the mover strip in the routing frame, in millimetres. */
export function stripBoundsDomainMm(
  config: { mover_span_mm: number },
  motion: { clampedPositionMm: number },
): { startMm: number; endMm: number } {
  const half = config.mover_span_mm / 2;
  return {
    startMm: motion.clampedPositionMm - half,
    endMm: motion.clampedPositionMm + half,
  };
}
