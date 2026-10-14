import { describe, expect, it } from "vitest";
import { warningClasses, warningLabel, pluralize, rippleStatus, formatSi } from "./format";

describe("warningClasses", () => {
  it("returns a distinct tailwind triple per severity", () => {
    const error = warningClasses("error");
    const warning = warningClasses("warning");
    const info = warningClasses("info");
    expect(error).toContain("rose");
    expect(warning).toContain("amber");
    expect(info).toContain("sky");
    const set = new Set([error, warning, info]);
    expect(set.size).toBe(3);
  });
});

describe("warningLabel", () => {
  it("uppercases the severity", () => {
    expect(warningLabel("error")).toBe("ERROR");
    expect(warningLabel("warning")).toBe("WARNING");
    expect(warningLabel("info")).toBe("INFO");
  });
});

describe("pluralize", () => {
  it("adds s only for counts ≠ 1", () => {
    expect(pluralize(1, "line")).toBe("1 line");
    expect(pluralize(0, "line")).toBe("0 lines");
    expect(pluralize(3, "line")).toBe("3 lines");
  });
});

describe("rippleStatus", () => {
  it("classifies ripple thresholds", () => {
    expect(rippleStatus(0)).toBe("ok");
    expect(rippleStatus(4.9)).toBe("ok");
    expect(rippleStatus(5)).toBe("warn");
    expect(rippleStatus(9.9)).toBe("warn");
    expect(rippleStatus(10)).toBe("bad");
    expect(rippleStatus(null)).toBe("na");
    expect(rippleStatus(undefined)).toBe("na");
    expect(rippleStatus(Number.NaN)).toBe("na");
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
