import { describe, expect, it } from "vitest";
import {
  automaticTimeStep, buildMoveRequest, defaultMoveForm, moveAnalysisConfig, moveFormFromRequest, moveFormIssues,
  type MoveDesignDefaults,
} from "./moveForm";

const design: MoveDesignDefaults = {
  fullTravelMm: 63,
  magnetWidthMm: 4,
  massG: 15,
  frictionN: 0.05,
  massSource: "assembly",
};

describe("move form", () => {
  it("suggests the full travel and a half-second move without storing anything", () => {
    const form = defaultMoveForm(design);
    expect(form.fromMm).toBe(0);
    expect(form.toMm).toBe(63);
    expect(form.durationS).toBe(0.5);
    expect(form.loadMode).toBe("design");
    expect(moveFormIssues(form, design)).toEqual([]);
  });

  it("converts millimetres, grams and seconds to the native request once", () => {
    const form = defaultMoveForm(design);
    form.toMm = 60;
    const request = buildMoveRequest(form, { design });
    expect(request.profile.start_m).toBeCloseTo(0.002, 12);
    expect(request.profile.end_m).toBeCloseTo(0.062, 12);
    expect(request.profile.travel_min_m).toBeCloseTo(0.002, 12);
    expect(request.profile.travel_max_m).toBeCloseTo(0.062, 12);
    expect(request.profile.moving_mass_kg).toBeCloseTo(0.015, 12);
    expect(request.profile.coulomb_friction_n).toBeCloseTo(0.05, 12);
    expect(request.profile.duration_s).toBe(0.5);
    expect(request.profile.time_step_s).toBeCloseTo(0.00025, 12);
    expect(request.profile.mass_includes).toContain("Full moving assembly");
    expect(request.control).toBe("balanced_star_sinusoidal");
    expect(request.force_positions).toBe(129);
    expect(request.loss_model).toBeNull();
  });

  it("keeps an existing saved move's own values and round-trips them", () => {
    const form = defaultMoveForm(design);
    form.fromMm = 10;
    form.toMm = 42.5;
    form.durationS = 0.75;
    form.loadMode = "custom";
    form.massG = 22.5;
    form.frictionN = 0.08;
    form.advanced.initialVelocityMPerS = 0.02;
    form.advanced.finalVelocityMPerS = -0.01;
    form.advanced.acceptsRegeneration = false;
    form.advanced.electricalAngleRad = 1.25;
    form.advanced.forcePositions = 65;
    form.advanced.timeStepS = 0.0005;
    const request = buildMoveRequest(form, { design });
    const restored = moveFormFromRequest(request, design);
    expect(restored.fromMm).toBeCloseTo(10, 9);
    expect(restored.toMm).toBeCloseTo(42.5, 9);
    expect(restored.durationS).toBe(0.75);
    expect(restored.loadMode).toBe("custom");
    expect(restored.massG).toBeCloseTo(22.5, 9);
    expect(restored.frictionN).toBeCloseTo(0.08, 12);
    expect(restored.advanced.acceptsRegeneration).toBe(false);
    expect(restored.advanced.electricalAngleRad).toBe(1.25);
    expect(restored.advanced.forcePositions).toBe(65);
    expect(restored.advanced.timeStepS).toBe(0.0005);
  });

  it("recognises the design load again after a round trip", () => {
    const request = buildMoveRequest(defaultMoveForm(design), { design });
    const restored = moveFormFromRequest(request, design);
    expect(restored.loadMode).toBe("design");
  });

  it("reports actionable problems instead of building an invalid request", () => {
    const form = defaultMoveForm(design);
    form.toMm = 70;
    expect(moveFormIssues(form, design).join(" ")).toContain("outside the 63 mm usable travel");
    expect(() => buildMoveRequest(form, { design })).toThrow("outside");

    const same = defaultMoveForm(design);
    same.toMm = 0;
    expect(moveFormIssues(same, design).join(" ")).toContain("must differ");

    const timing = defaultMoveForm(design);
    timing.advanced.timeStepS = 1e-7;
    expect(moveFormIssues(timing, design).join(" ")).toContain("20,000 samples");

    const custom = defaultMoveForm(design);
    custom.loadMode = "custom";
    custom.massG = null;
    expect(moveFormIssues(custom, design).join(" ")).toContain("moving mass");
  });

  it("allows a reverse move as a separate monotonic request", () => {
    const form = defaultMoveForm(design);
    form.fromMm = 60;
    form.toMm = 0;
    const request = buildMoveRequest(form, { design });
    expect(request.profile.start_m).toBeCloseTo(0.062, 12);
    expect(request.profile.end_m).toBeCloseTo(0.002, 12);
    expect(request.profile.travel_min_m).toBeCloseTo(0.002, 12);
  });

  it("excludes the stack only in an analysis copy", () => {
    const config = { backplane: { layers: [{ material: "flex_ferrite", thickness_m: 0.0002 }], housing: null } };
    const excluded = moveAnalysisConfig(config, true);
    expect(excluded.backplane).toBeNull();
    expect(config.backplane).not.toBeNull();
    expect(moveAnalysisConfig(config, false)).toBe(config);
    expect(moveAnalysisConfig({ backplane: null }, true).backplane).toBeNull();
  });

  it("bounds the automatic step to a practical sample count", () => {
    expect(automaticTimeStep(0.5)).toBeCloseTo(0.00025, 12);
    expect(automaticTimeStep(0.001)).toBeCloseTo(1e-4, 12);
    expect(automaticTimeStep(10)).toBe(1e-3);
  });
});
