/** Phase-band pitch: vernier fraction of the pole pitch per phase. */
export function phaseBandPitchMm(
  polePitchMm: number,
  phases: number,
  spacingRatio: number,
): number {
  return (polePitchMm / phases) * spacingRatio;
}

/** Rest-position drift per phase band for a reduced vernier ratio. */
export function restOffsetMm(
  polePitchMm: number,
  phases: number,
  spacingRatio: number,
): number {
  return Math.max(0, (polePitchMm / phases) * (1 - spacingRatio));
}
