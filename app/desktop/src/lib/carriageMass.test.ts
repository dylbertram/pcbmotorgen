import { describe, expect, it } from "vitest";
import { magnetMass } from "./carriageMass";
import { ConfigStore } from "./stores/config.svelte";

describe("carriage mass estimates", () => {
  it("uses the supplied N52 reference and an explicit volume estimate for other sizes", () => {
    expect(magnetMass([5, 5, 3], "N52")).toEqual({ massG: 0.57, source: "User-supplied reference", estimated: false });
    expect(magnetMass([3, 5, 5], "N52").massG).toBe(0.57);
    expect(magnetMass([10, 5, 3], "N52").massG).toBeCloseTo(1.14, 12);
    expect(magnetMass([5, 5, 3], "N44").estimated).toBe(true);
  });

  it("defaults to all magnets and tracks geometry until the user overrides the whole assembly", () => {
    const c = new ConfigStore();
    c.magnet_width_mm = 5;
    c.magnet_cross_width_mm = 5;
    c.magnet_height_mm = 3;
    c.magnet_grade = "N52";
    c.magnet_count = 10;
    expect(c.carriage_mass_source).toBe("magnets");
    expect(c.carriage_mass_kg).toBeCloseTo(0.0057, 12);
    expect(c.toIpc().carriage_mass_kg).toBeCloseTo(0.0057, 12);
    c.magnet_count = 12;
    expect(c.carriage_mass_kg).toBeCloseTo(0.00684, 12);
    c.carriage_mass_kg = 0.015;
    expect(c.carriage_mass_source).toBe("assembly");
    c.magnet_height_mm = 6;
    expect(c.carriage_mass_kg).toBe(0.015);
    expect(c.toIpc().carriage_mass_kg).toBe(0.015);
    c.carriage_mass_source = "magnets";
    expect(c.carriage_mass_kg).toBeCloseTo(0.01368, 12);
  });
});
