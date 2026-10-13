import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DEFAULT_RULES } from "./preferences";
import { importKicadDrc } from "./kicadDrc";

const load = (body: string) => importKicadDrc(`(version 1)\n${body}`, DEFAULT_RULES);

describe("KiCad DRC import", () => {
  it("imports the active PCBWay rules, not commented alternatives or pad rules", () => {
    const example = readFileSync(new URL("../../e2e/fixtures/pcbway.kicad_dru", import.meta.url), "utf8");
    const result = importKicadDrc(example, DEFAULT_RULES);
    expect(result.rules).toEqual({
      min_trace_mm: 0.127,
      min_space_mm: 0.127,
      min_via_drill_mm: 0.3,
      min_via_annular_ring_mm: 0.1,
    });
    expect(result.warnings.join(" ")).toContain("Layer-specific");
    expect(result.warnings.join(" ")).toContain('Skipped conditional or disabled rule "Pad Size"');
    expect(result.warnings.join(" ")).toContain("Maximum and preferred");
  });

  it("uses the strictest minimum, converts units, and preserves missing fields", () => {
    const result = load(`
      # (rule "inactive" (constraint track_width (min 5mm)))
      (rule "outer" (constraint track_width (min 5mil)))
      (rule "inner" (constraint track_width (min 0.2mm)))
      (rule "spacing" (constraint clearance (min 0.01in)))
    `);
    expect(result.rules).toEqual({ min_trace_mm: 0.2, min_space_mm: 0.254 });
  });

  it("accepts escaped quotes and comment markers inside rule names", () => {
    expect(load('(rule "name # with \\"quotes\\"" (constraint track_width (min .2mm)))').rules.min_trace_mm).toBe(0.2);
  });

  it("skips complex conditions and ignored rules rather than treating them as global", () => {
    const result = load(`
      (rule "global" (constraint clearance (min .1mm)))
      (rule "net" (condition "A.Net == 'special'") (constraint clearance (min 1mm)))
      (rule "disabled" (severity ignore) (constraint track_width (min 2mm)))
    `);
    expect(result.rules).toEqual({ min_space_mm: 0.1 });
    expect(result.warnings.join(" ")).toContain('"net"');
    expect(result.warnings.join(" ")).toContain('"disabled"');
  });

  it("derives ring width using the imported drill regardless of rule order", () => {
    expect(load(`
      (rule "diameter" (constraint via_diameter (min .7mm)))
      (rule "drill" (constraint hole_size (min .3mm)) (condition "A.Type == 'Via'"))
    `).rules).toEqual({ min_via_drill_mm: 0.3, min_via_annular_ring_mm: 0.2 });
    expect(load('(rule "ring" (constraint annular_width (min .15mm)))').rules.min_via_annular_ring_mm).toBe(0.15);
    expect(() => importKicadDrc('(version 1) (rule "diameter" (constraint via_diameter (min .5mm)))', { ...DEFAULT_RULES, min_via_drill_mm: 0 })).toThrow(/positive minimum via drill/);
  });

  it.each([
    "", "(version 2)", "(version 1) (rule", '(version 1) (rule "unterminated)',
    '(version 1) (rule "bad" (constraint track_width (min -1mm)))',
    '(version 1) (rule "bad" (constraint clearance (min 0mm)))',
    '(version 1) (rule "bad" (constraint clearance (min 1cm)))',
    '(version 1) (rule "unsupported" (constraint silk_clearance (min 1mm)))',
    '(version 1) (rule "bad" unexpected)',
  ])("rejects invalid or unsupported files without changing current rules: %s", text => {
    const current = { ...DEFAULT_RULES };
    expect(() => importKicadDrc(text, current)).toThrow();
    expect(current).toEqual(DEFAULT_RULES);
  });
});
