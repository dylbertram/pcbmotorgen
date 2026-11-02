import { describe, expect, it } from "vitest";
import type { PhaseBandWidthDto } from "../types";
import { braidLikeFixture } from "../testFixtures/braidLike";
import { computeBandWidthRows, medianActiveConductorX } from "./bandWidth";

function band(layer: number, net: string, width: number, max: number | null = null, margin: number | null = null): PhaseBandWidthDto {
  return {
    layer, net, trace_count: 1, trace_width_m: 0.0002, trace_spacing_m: 0.0002,
    angle_rad: Math.PI / 2, band_width_m: width, slot_width_m: null,
    max_band_width_m: max, margin_m: margin,
  };
}

describe("computeBandWidthRows", () => {
  it("returns [] while the sidecar is missing", () => {
    expect(computeBandWidthRows(braidLikeFixture(), null)).toEqual([]);
    expect(computeBandWidthRows(null, { phase_band_widths: [] })).toEqual([]);
  });

  it("matches each record to its (layer, net) phase coil", () => {
    const rows = computeBandWidthRows(braidLikeFixture(), {
      phase_band_widths: [
        band(0, "A", 0.002, 0.004, 0.002),
        band(1, "B", 0.003, 0.0025, -0.0005),
        band(0, "C", 0.002, null, null),
        band(0, "D", 0.002, 0.004, 0.002),
      ],
    });
    expect(rows).toHaveLength(3);
    const a = rows.find((r) => r.phaseName === "A")!;
    expect(a.phaseIdx).toBe(0);
    expect(a.layer).toBe(0);
    expect(a.anchorX).toBeCloseTo(0.006, 9);
    expect(a.bandM).toBeCloseTo(0.002, 9);
    expect(a.maxM).toBeCloseTo(0.004, 9);
    expect(a.marginM).toBeCloseTo(0.002, 9);
    expect(a.status).toBe("ok");
    const b = rows.find((r) => r.phaseName === "B")!;
    expect(b.phaseIdx).toBe(1);
    expect(b.status).toBe("over-budget");
    const c = rows.find((r) => r.phaseName === "C")!;
    expect(c.status).toBe("no-limit");
    expect(c.maxM).toBeNull();
    expect(c.marginM).toBeNull();
  });

  it("skips records with invalid band widths", () => {
    const rows = computeBandWidthRows(braidLikeFixture(), {
      phase_band_widths: [band(0, "A", 0), band(0, "A", Number.NaN), band(0, "A", -0.001)],
    });
    expect(rows).toEqual([]);
  });

  it("keeps a finite zero/negative limit visible as an over-budget diagnostic", () => {
    const rows = computeBandWidthRows(braidLikeFixture(), {
      phase_band_widths: [band(0, "A", 0.002, 0, -0.002)],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].maxM).toBe(0);
    expect(rows[0].marginM).toBe(-0.002);
    expect(rows[0].status).toBe("over-budget");
  });

  it("stacks matched rows symmetrically around the conductor rail", () => {
    const rows = computeBandWidthRows(braidLikeFixture(), {
      phase_band_widths: [band(0, "A", 0.002), band(1, "A", 0.002)],
    });
    expect(rows).toHaveLength(2);
    expect(rows[0].y).toBeCloseTo(0.01 - 0.0005, 9);
    expect(rows[1].y).toBeCloseTo(0.01 + 0.0005, 9);
  });
});

describe("medianActiveConductorX", () => {
  it("returns the median active conductor x, ignoring end-turns", () => {
    const phase = braidLikeFixture().phases.find((p) => p.phase_idx === 1 && p.layer_idx === 0)!;
    expect(medianActiveConductorX(phase)).toBeCloseTo(0.009, 9);
  });
});
