import { formatMarginMm, formatMetresMm } from "../../../format";

type Span = [number, number] | null;

/** Summarize finite band values, treating differences within 1e-12 m as equal. */
export function bandValueSpan(values: (number | null | undefined)[]): Span {
  let min = Infinity;
  let max = -Infinity;
  for (const value of values) {
    if (typeof value !== "number" || !Number.isFinite(value)) continue;
    min = Math.min(min, value);
    max = Math.max(max, value);
  }
  if (!Number.isFinite(min)) return null;
  return max - min <= 1e-12 ? [min, min] : [min, max];
}

function formatSpan(span: Span, format: (value: number) => string): string {
  if (!span) return "—";
  return span[0] === span[1] ? format(span[0]) : `${format(span[0])} – ${format(span[1])}`;
}

export function formatSpanMm(span: Span): string {
  return formatSpan(span, formatMetresMm);
}

export function formatMarginSpanMm(span: Span): string {
  return formatSpan(span, formatMarginMm);
}
