import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_RULES } from "./preferences";
import { readRulesets, rulesetValidationError, saveRulesets } from "./drcRulesets";

const KEY = "pcbmotorgen.drc_rulesets.v1";

afterEach(() => vi.unstubAllGlobals());

describe("drc rulesets", () => {
  it("retains legacy named rulesets with a customized trace width", () => {
    vi.stubGlobal("localStorage", { getItem: () => JSON.stringify([{ name: "Legacy", rules: {
      min_trace_mm: 0.3, min_space_mm: 0.2, min_via_drill_mm: 0.4, min_via_annular_ring_mm: 0.1,
    } }]) });
    expect(readRulesets()).toEqual([{ name: "Legacy", rules: {
      min_trace_mm: 0.3, trace_width_mm: 0.3, min_space_mm: 0.2, min_via_drill_mm: 0.4, min_via_annular_ring_mm: 0.1,
    } }]);
  });

  it("reads an empty list without storage or with corrupt data", () => {
    expect(readRulesets()).toEqual([]);
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    });
    for (const raw of ["{bad", "null", "{}", JSON.stringify([{ name: "", rules: DEFAULT_RULES }, { name: "ok", rules: { ...DEFAULT_RULES, min_space_mm: -1 } }])]) {
      values.set(KEY, raw);
      expect(readRulesets()).toEqual([]);
    }
  });

  it("round-trips valid rulesets and drops malformed neighbours", () => {
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    });
    const ruleset = { name: "PCBWay", rules: { ...DEFAULT_RULES, min_space_mm: 0.2 } };
    expect(saveRulesets([ruleset, { name: "broken", rules: { ...DEFAULT_RULES, min_trace_mm: 0 } } as never])).toBe(true);
    expect(readRulesets()).toEqual([ruleset]);
  });

  it("reports the first validation problem", () => {
    expect(rulesetValidationError({ name: "  ", rules: DEFAULT_RULES })).toMatch(/name/i);
    expect(rulesetValidationError({ name: "ok", rules: { ...DEFAULT_RULES, min_via_drill_mm: NaN } })).toMatch(/positive/);
    expect(rulesetValidationError({ name: "ok", rules: { ...DEFAULT_RULES } })).toBeNull();
  });

  it("returns false when storage is unavailable", () => {
    vi.stubGlobal("localStorage", { setItem: () => { throw new Error("full"); } });
    expect(saveRulesets([{ name: "x", rules: { ...DEFAULT_RULES } }])).toBe(false);
  });
});
