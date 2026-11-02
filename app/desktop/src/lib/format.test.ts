import { describe, expect, it } from "vitest";
import { formatSi, formatMetresMm, formatMarginMm } from "./format";

describe("formatMetresMm / formatMarginMm", () => {
  it("formats metre lengths as compact mm", () => {
    expect(formatMetresMm(0.012)).toBe("12.0 mm");
    expect(formatMetresMm(0.001777)).toBe("1.78 mm");
    expect(formatMetresMm(0.0002)).toBe("0.200 mm");
    expect(formatMetresMm(Number.NaN)).toBe("—");
  });

  it("formats signed slot margins", () => {
    expect(formatMarginMm(0.002)).toBe("+2.00 mm");
    expect(formatMarginMm(-0.0005)).toBe("-0.500 mm");
  });
});

describe("formatSi", () => {
  it("picks the prefix and keeps significant digits", () => {
    expect(formatSi(2.2e-6, "H")).toBe("2.20 µH");
    expect(formatSi(100e3, "Hz")).toBe("100 kHz");
    expect(formatSi(1.046, "Ω")).toBe("1.05 Ω");
    expect(formatSi(0.0015, "Ω")).toBe("1.50 mΩ");
    expect(formatSi(0, "A")).toBe("0 A");
    expect(formatSi(Infinity, "A")).toBe("—");
  });
});
