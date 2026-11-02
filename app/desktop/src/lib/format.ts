/**
 * Presentation formatting helpers shared by panels.
 */

/** Format a metre length as a compact mm string, e.g. "12 mm" / "1.78 mm". */
export function formatMetresMm(v: number): string {
  if (!Number.isFinite(v)) return "—";
  const mmV = Math.abs(v * 1000);
  const digits = mmV >= 100 ? 0 : mmV >= 10 ? 1 : mmV >= 1 ? 2 : 3;
  return `${(v * 1000).toFixed(digits)} mm`;
}

/** Signed mm formatter for band margins, e.g. "+0.28 mm" / "-0.10 mm". */
export function formatMarginMm(v: number): string {
  const magnitude = formatMetresMm(Math.abs(v));
  return v < 0 ? `-${magnitude}` : `+${magnitude}`;
}

const SI_PREFIXES: [number, string][] = [
  [1e6, "M"],
  [1e3, "k"],
  [1, ""],
  [1e-3, "m"],
  [1e-6, "µ"],
  [1e-9, "n"],
];

/**
 * Engineering notation with an SI prefix: `formatSi(2.2e-6, "H")` → "2.20 µH".
 * `digits` is the number of significant digits (default 3). Non-finite
 * values render as "—".
 */
export function formatSi(value: number | null | undefined, unit: string, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value === 0) return `0 ${unit}`;
  const abs = Math.abs(value);
  const [factor, prefix] = SI_PREFIXES.find(([f]) => abs >= f * 0.9995) ?? SI_PREFIXES[SI_PREFIXES.length - 1];
  const scaled = value / factor;
  const decimals = Math.max(0, digits - 1 - Math.floor(Math.log10(Math.abs(scaled))));
  return `${scaled.toFixed(decimals)} ${prefix}${unit}`;
}
