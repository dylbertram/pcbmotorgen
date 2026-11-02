/**
 * Tests for the normalized per-phase holding-force profile used by the
 * position-slider chart: F_p(x) = −sin(2π(x − φ − p·P_e/N)/P_e).
 */

import { describe, expect, it } from "vitest";
import {
  holdingForceAt,
  holdingForceAtPhase,
  sampleHoldingForce,
  restPositions,
  phaseStroke,
} from "./holdingForce";

describe("holdingForceAt", () => {
  it("zeros exactly at the rest phase and at every period multiple", () => {
    const phi = 10;
    const pe = 12;
    expect(holdingForceAt(phi, phi, pe)).toBeCloseTo(0, 12);
    expect(holdingForceAt(phi + pe, phi, pe)).toBeCloseTo(0, 12);
    expect(holdingForceAt(phi - 2 * pe, phi, pe)).toBeCloseTo(0, 12);
  });

  it("has negative slope at the rest positions (restoring force)", () => {
    const phi = 10;
    const pe = 12;
    const before = holdingForceAt(phi - 0.01, phi, pe);
    const after = holdingForceAt(phi + 0.01, phi, pe);
    expect(before).toBeGreaterThan(0);
    expect(after).toBeLessThan(0);
  });

  it("peaks midway between rest positions with amplitude ±1", () => {
    const phi = 10;
    const pe = 12;
    expect(holdingForceAt(phi + pe / 4, phi, pe)).toBeCloseTo(-1, 12);
    expect(holdingForceAt(phi + (3 * pe) / 4, phi, pe)).toBeCloseTo(1, 12);
  });

  it("returns 0 for a non-positive period", () => {
    expect(holdingForceAt(5, 0, 0)).toBe(0);
    expect(holdingForceAt(5, 0, -3)).toBe(0);
  });
});

describe("sampleHoldingForce", () => {
  it("samples n inclusive points across the range", () => {
    const { xs, ys } = sampleHoldingForce(10, 22, 10, 12, 5);
    expect(xs).toHaveLength(5);
    expect(xs[0]).toBeCloseTo(10, 12);
    expect(xs[4]).toBeCloseTo(22, 12);
    // Both endpoints are rest positions → zero force.
    expect(ys[0]).toBeCloseTo(0, 12);
    expect(ys[4]).toBeCloseTo(0, 12);
  });

  it("guards degenerate ranges", () => {
    const { xs } = sampleHoldingForce(Number.NaN, 20, 0, 12, 4);
    expect(xs[0]).toBe(0);
    // A collapsed range is widened to a 1 mm span so the chart still draws.
    const single = sampleHoldingForce(5, 5, 0, 12, 4);
    expect(single.xs[0]).toBe(5);
    expect(single.xs[single.xs.length - 1]).toBe(6);
  });
});

describe("restPositions", () => {
  it("lists every x ≡ φ (mod P_e) inside the range", () => {
    expect(restPositions(10, 46, 10, 12)).toEqual([10, 22, 34, 46]);
  });

  it("handles ranges that start/end between rest positions", () => {
    expect(restPositions(11, 45, 10, 12)).toEqual([22, 34]);
  });

  it("returns [] for a non-positive period or inverted range", () => {
    expect(restPositions(0, 10, 0, 0)).toEqual([]);
    expect(restPositions(10, 0, 0, 12)).toEqual([]);
  });
});

describe("holdingForceAtPhase (per-phase waves)", () => {
  const PE = 12;

  it("offsets each phase by P_e/N in space (120° for 3 phases)", () => {
    // Phase A zero at φ; phase B zero at φ + 4; phase C zero at φ + 8.
    // Pinned reference rest phase (authority:
    // `equilibrium::travel_envelope_over_slots`; the TS re-derivation
    // `fallbackRestPhaseMm` was removed by kata ab30).
    const phi = 10;
    expect(holdingForceAtPhase(phi, 0, 3, phi, PE)).toBeCloseTo(0, 12);
    expect(holdingForceAtPhase(phi + 4, 1, 3, phi, PE)).toBeCloseTo(0, 12);
    expect(holdingForceAtPhase(phi + 8, 2, 3, phi, PE)).toBeCloseTo(0, 12);
  });

  it("phase B at phase A's zero sits at 120° → amplitude √3⁄2", () => {
    const phi = 10;
    // F_B(φ) = −sin(−2π·(P_e/3)/P_e) = sin(120°) = √3/2
    const b = holdingForceAtPhase(phi, 1, 3, phi, PE);
    expect(b).toBeCloseTo(Math.sqrt(3) / 2, 12);
  });

  it("degenerates to the baseline wave for a single phase", () => {
    expect(holdingForceAtPhase(13, 0, 1, 10, PE)).toBeCloseTo(holdingForceAt(13, 10, PE), 12);
  });
});

describe("phase palette", () => {
  it("cycles stroke classes for phases beyond the palette size", () => {
    expect(phaseStroke(0)).toContain("emerald");
    expect(phaseStroke(1)).toContain("sky");
    expect(phaseStroke(2)).toContain("violet");
    expect(phaseStroke(3)).toBe(phaseStroke(0));
  });
});
