export interface PcbStackupMm { copper_mm: number[]; dielectric_mm: number[] }
export interface PcbStackupSi { copper_m: number[]; dielectric_m: number[] }

export function pcbStackupThicknessMm(stack: PcbStackupMm): number {
  return [...stack.copper_mm, ...stack.dielectric_mm].reduce((a, b) => a + b, 0);
}

export function validatePcbStackup(stack: PcbStackupMm, layers: number, totalMm = pcbStackupThicknessMm(stack)): void {
  if (layers < 2 || layers > 16 || stack.copper_mm.length !== layers || stack.dielectric_mm.length !== layers - 1)
    throw new Error(`Stackup must contain ${layers} copper layers and ${layers - 1} dielectric layers.`);
  if ([...stack.copper_mm, ...stack.dielectric_mm].some(t => !Number.isFinite(t) || t <= 0))
    throw new Error("Every copper and dielectric thickness must be positive and finite.");
  const actual = pcbStackupThicknessMm(stack);
  if (!Number.isFinite(totalMm) || !Number.isFinite(actual) || Math.abs(actual - totalMm) > 1e-7)
    throw new Error("PCB thickness must equal the sum of the copper and dielectric layers.");
}

export function pcbStackupHeightsMm(stack: PcbStackupMm): number[] {
  validatePcbStackup(stack, stack.copper_mm.length);
  let depth = 0;
  return stack.copper_mm.map((copper, i) => {
    const z = -depth - copper / 2;
    depth += copper + (stack.dielectric_mm[i] ?? 0);
    return z;
  });
}

export function initialPcbStackup(layers: number, totalMm: number, outerOz: number, innerOz: number): PcbStackupMm {
  const copper_mm = Array.from({ length: layers }, (_, i) => (i === 0 || i === layers - 1 ? outerOz : innerOz) * .035);
  const dielectric = (totalMm - copper_mm.reduce((a, b) => a + b, 0)) / (layers - 1);
  const stack = { copper_mm, dielectric_mm: Array(layers - 1).fill(dielectric) };
  validatePcbStackup(stack, layers, totalMm);
  return stack;
}

export function pcbStackupToSi(stack: PcbStackupMm): PcbStackupSi {
  return { copper_m: stack.copper_mm.map(t => t / 1000), dielectric_m: stack.dielectric_mm.map(t => t / 1000) };
}
