import { describe, expect, it } from "vitest";
import { validateDesign, hasErrors, type DesignConfigInput } from "./validation";

/** Valid baseline — all checks should pass. */
function validConfig(overrides: Partial<DesignConfigInput> = {}): DesignConfigInput {
  return {
    travel_mm: 75,
    mover_span_mm: 72,
    magnet_count: 12,
    magnet_width_mm: 4.5,
    magnet_gap_mm: 1.5,
    electrical_pitch_mm: 12.0,
    min_space_mm: 0.127,
    magnet_cross_width_mm: 10,
    active_area_width_mm: 20,
    num_layers: 4,
    max_layers: 12,
    routing_pattern: "infinity-braid",
    strands_per_phase: 2,
    min_trace_mm: 0.127,
    trace_width_mm: 0.127,
    peak_force_n: 1.0,
    target_force_n: 0.5,
    ...overrides,
  };
}

const ids = (config: DesignConfigInput) => validateDesign(config).map((f) => f.id);

describe("validateDesign", () => {
  it("returns no findings for a valid config", () => {
    expect(validateDesign(validConfig())).toEqual([]);
  });

  it("flags a nominal trace width below the minimum", () => {
    expect(ids(validConfig({ trace_width_mm: 0.1 }))).toContain("trace-width");
    expect(ids(validConfig({ trace_width_mm: 0 }))).toContain("trace-width");
    expect(ids(validConfig({ trace_width_mm: 0.2 }))).not.toContain("trace-width");
  });

  it("flags non-positive travel as an error", () => {
    expect(ids(validConfig({ travel_mm: 0 }))).toContain("travel-negative");
    expect(ids(validConfig({ travel_mm: -10 }))).toContain("travel-negative");
    expect(ids(validConfig({ travel_mm: Number.NaN }))).toContain("travel-negative");
  });

  it("accepts both odd and even magnet counts ≥ 2", () => {
    for (const magnet_count of [2, 3, 5, 8, 9]) {
      expect(ids(validConfig({ magnet_count }))).not.toContain("magnet-count");
    }
  });

  it("rejects magnet counts below two or non-integer counts", () => {
    for (const magnet_count of [-1, 0, 1, 2.5, Number.NaN, Infinity]) {
      const finding = validateDesign(validConfig({ magnet_count })).find((f) => f.id === "magnet-count");
      expect(finding?.level).toBe("error");
      expect(finding?.message).toContain("integer ≥ 2");
    }
  });

  it("requires a positive electrical pitch", () => {
    expect(ids(validConfig({ electrical_pitch_mm: 0 }))).toContain("electrical-pitch");
    expect(ids(validConfig({ electrical_pitch_mm: -1 }))).toContain("electrical-pitch");
  });

  it("derives k from the magnet width and rejects it outside [0.50, 1.00]", () => {
    // 6 mm pole pitch (12 mm electrical pitch): 2 mm / 6 mm = k ≈ 0.33 → error.
    expect(ids(validConfig({ magnet_width_mm: 2 }))).toContain("magnet-fill");
    // 7 mm / 6 mm = k ≈ 1.17 → error.
    expect(ids(validConfig({ magnet_width_mm: 7 }))).toContain("magnet-fill");
    // Degenerate pitch makes k undefined → error.
    expect(
      ids(validConfig({ electrical_pitch_mm: 0, magnet_width_mm: 4.5 })),
    ).toContain("magnet-fill");
    // 3–6 mm at the 6 mm pole pitch is the allowed band.
    expect(ids(validConfig({ magnet_width_mm: 3 }))).not.toContain("magnet-fill");
    expect(ids(validConfig({ magnet_width_mm: 6 }))).not.toContain("magnet-fill");
  });

  it("warns above k = 0.85 but still allows end-to-end magnets (k = 1.00)", () => {
    const findings = validateDesign(validConfig({ magnet_width_mm: 6 }));
    expect(findings.find((f) => f.id === "magnet-fill-leakage")?.level).toBe("warning");
    expect(ids(validConfig({ magnet_width_mm: 6 }))).not.toContain("magnet-fill");
    // Default 4.5 mm @ 6 mm pitch → k = 0.75: clean.
    expect(validateDesign(validConfig())).toEqual([]);
  });

  it("warns when the magnet cross width exceeds the active area width", () => {
    const findings = validateDesign(validConfig({ magnet_cross_width_mm: 25 }));
    expect(findings.find((f) => f.id === "magnet-cross-width")?.level).toBe("warning");
  });

  it("requires an even layer count within the configured maximum", () => {
    expect(ids(validConfig({ num_layers: 3 }))).toContain("layer-count");
    expect(ids(validConfig({ num_layers: 6 }))).not.toContain("layer-count");
    const over = validateDesign(validConfig({ num_layers: 14 }));
    expect(over.find((f) => f.id === "layer-limit")?.level).toBe("error");
  });

  it("requires two layers for the infinity braid", () => {
    expect(ids(validConfig({ num_layers: 2, routing_pattern: "infinity-braid" }))).not.toContain(
      "infinity-layer-requirement",
    );
    expect(ids(validConfig({ num_layers: 1, routing_pattern: "infinity-braid" }))).toContain(
      "infinity-layer-requirement",
    );
  });

  it("warns when multiple strands cannot fit trace + clearance", () => {
    const findings = validateDesign(validConfig({ strands_per_phase: 4 }));
    // 20mm / 4 = 5mm per strand — plenty of room
    expect(findings.find((f) => f.id === "strand-clearance")).toBeUndefined();
    const tight = validateDesign(validConfig({ active_area_width_mm: 0.4, strands_per_phase: 2 }));
    expect(tight.find((f) => f.id === "strand-clearance")?.level).toBe("warning");
  });

  it("warns when peak force is below the continuous target", () => {
    const findings = validateDesign(validConfig({ peak_force_n: 0.3, target_force_n: 0.5 }));
    expect(findings.find((f) => f.id === "force-target-order")?.level).toBe("warning");
  });
});

describe("hasErrors", () => {
  it("is true only when at least one finding is error-level", () => {
    expect(hasErrors(validateDesign(validConfig({ travel_mm: 0 })))).toBe(true);
    expect(hasErrors(validateDesign(validConfig({ magnet_cross_width_mm: 25 })))).toBe(false);
  });
});
