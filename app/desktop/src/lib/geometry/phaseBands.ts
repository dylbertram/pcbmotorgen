/** Phase-band pitch: vernier fraction of the pole pitch per phase. */
export function phaseBandPitchMm(
  polePitchMm: number,
  phases: number,
  spacingRatio: number,
): number {
  return (polePitchMm / phases) * spacingRatio;
}

/** Nominal minus configured band pitch, clamped to zero. */
export function phaseBandPitchDifferenceMm(
  polePitchMm: number,
  phases: number,
  spacingRatio: number,
): number {
  return Math.max(0, (polePitchMm / phases) * (1 - spacingRatio));
}
