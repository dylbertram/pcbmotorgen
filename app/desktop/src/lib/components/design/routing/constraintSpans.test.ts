import { describe, expect, it } from "vitest";
import { bandValueSpan, formatMarginSpanMm, formatSpanMm } from "./constraintSpans";

describe("constraint band spans", () => {
  it("ignores missing and non-finite values", () => {
    expect(bandValueSpan([null, undefined, NaN, Infinity, -Infinity])).toBeNull();
    expect(bandValueSpan([NaN, 0.003, null, -0.001])).toEqual([-0.001, 0.003]);
  });

  it("collapses differences up to the metre tolerance", () => {
    expect(bandValueSpan([0, 1e-12])).toEqual([0, 0]);
    expect(bandValueSpan([0, 1.01e-12])).toEqual([0, 1.01e-12]);
  });

  it("formats missing, single and varying values with signed margins", () => {
    expect(formatSpanMm(null)).toBe("—");
    expect(formatMarginSpanMm(null)).toBe("—");
    expect(formatSpanMm([0.001, 0.001])).toBe("1.00 mm");
    expect(formatSpanMm([0.001, 0.002])).toBe("1.00 mm – 2.00 mm");
    expect(formatMarginSpanMm([0, 0])).toBe("+0.000 mm");
    expect(formatMarginSpanMm([-0.001, 0.002])).toBe("-1.00 mm – +2.00 mm");
  });
});
