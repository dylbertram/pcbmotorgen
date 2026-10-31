/** Mass references are engineering inputs, not magnetic performance data. */
export const MAGNET_MASS_REFERENCES = [
  { dimensionsMm: [5, 5, 3] as const, grade: "N52", massG: 0.57, source: "User-supplied reference" },
];

// 0.57 g / 75 mm³. Use this approximate NdFeB density for unlisted sizes;
// do not invent vendor weights or grade-dependent density precision.
export const ESTIMATED_NDFEB_DENSITY_G_MM3 = 0.0076;

export function magnetMass(dimensionsMm: readonly number[], grade: string) {
  const dimensions = [...dimensionsMm].sort((a, b) => a - b);
  const reference = MAGNET_MASS_REFERENCES.find(entry => entry.grade === grade &&
    [...entry.dimensionsMm].sort((a, b) => a - b).every((v, i) => v === dimensions[i]));
  const massG = reference?.massG ?? dimensionsMm.reduce((volume, length) => volume * length, 1) * ESTIMATED_NDFEB_DENSITY_G_MM3;
  return { massG, source: reference?.source ?? "Volume estimate at 7.6 g/cm³", estimated: !reference };
}
