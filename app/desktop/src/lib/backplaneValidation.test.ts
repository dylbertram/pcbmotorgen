import { describe, expect, it } from "vitest";
import { validateBackplaneInput } from "./validation";
import type { BackplaneStack } from "./types/backplane";

describe("coreless backplane restored-input validation", () => {
  it("accepts three layers each 2mm, 5mm housing and 10mm gap without an aggregate 2mm cap", () => {
    const stack: BackplaneStack = { layers: Array.from({ length: 3 }, () => ({ material: "flex_ferrite", thickness_m: .002 })), housing: { material: "stainless316", thickness_m: .005, gap_m: .01 } };
    expect(validateBackplaneInput(stack)).toEqual([]);
  });
  it("reports legacy values without modifying saved geometry or material", () => {
    const stack: BackplaneStack = { layers: Array.from({ length: 4 }, () => ({ material: "flex_ferrite", thickness_m: .005 })), housing: { material: "steel1018", thickness_m: .02, gap_m: .02 } };
    const before = JSON.stringify(stack);
    const findings = validateBackplaneInput(stack);
    expect(findings.some((finding) => finding.id === "backplane-layer-limit")).toBe(true);
    expect(findings.some((finding) => finding.id === "housing-material")).toBe(true);
    expect(findings.some((finding) => finding.id === "housing-thickness")).toBe(true);
    expect(findings.some((finding) => finding.id === "housing-gap")).toBe(true);
    expect(JSON.stringify(stack)).toBe(before);
  });
  it("rejects nonfinite layer and gap inputs", () => {
    expect(validateBackplaneInput({ layers: [{ material: "fr4", thickness_m: Number.NaN }], housing: { material: "aluminum6061", thickness_m: .001, gap_m: Infinity } })).toHaveLength(2);
  });
});
