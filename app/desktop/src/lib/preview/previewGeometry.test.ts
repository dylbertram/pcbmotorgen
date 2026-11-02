/**
 * Unit tests for preview geometry and its overlay integration.
 * Covers overlaid layers, magnet strip placement, phase deduplication,
 * and overlay fit bounds.
 */

import { describe, expect, it } from "vitest";
import {
  computeFootprintBox,
  computeMagnets,
  computePreviewGeometry,
  computePreviewSummary,
  computeUniqueLayers,
  computeUniquePhases,
  computeOverlayFitBounds,
  computeMoverStripBounds,
  computeMagnetStartX,
  measureTrace,
  traceExtentMetres,
} from "./previewGeometry";
import { computePolePitchRuler } from "./polePitch";
import { computePoleRegionZones, computePoleRegionBounds } from "./poleRegions";
import { braidLikeFixture } from "../testFixtures/braidLike";
import type { PoleRegionDto } from "../types";

/** Default-config-like magnet layout (12 poles, 6 mm pole pitch: P_e/2). */
const CONFIG = { magnet_count: 12, magnet_width_mm: 4.5, magnet_gap_mm: 1.5 };

describe("preview status summary", () => {
  it("handles geometry that has not been generated", () => {
    expect(computePreviewSummary(null)).toBe("no coils yet");
  });
  it("counts distinct phases and layers while preserving coil group count", () => {
    expect(computePreviewSummary(braidLikeFixture())).toBe("3 phases · 2 layers · 6 coil groups");
  });
  it("uses singular labels for one phase, layer and group", () => {
    const coils = braidLikeFixture();
    coils.phases = coils.phases.slice(0, 1);
    expect(computePreviewSummary(coils)).toBe("1 phase · 1 layer · 1 coil group");
  });
});

describe("computeFootprintBox", () => {
  it("unions raw winding bounds without layer offsets", () => {
    const box = computeFootprintBox(braidLikeFixture());
    // Phases 0..2 at offset 0..0.006; conductors at x up to 0.006 + 3 * 0.004
    expect(box.minX).toBeCloseTo(0, 9);
    expect(box.maxX).toBeCloseTo(0.018, 9);
    expect(box.minY).toBeCloseTo(0, 9);
    expect(box.maxY).toBeCloseTo(0.021, 9);
  });

  it("includes corner-arc extremes", () => {
    const box = computeFootprintBox(braidLikeFixture());
    expect(box.maxY).toBeCloseTo(0.021, 9);
    expect(box.maxX).toBeCloseTo(0.018, 9);
  });

  it("is degenerate-safe with no coils", () => {
    const box = computeFootprintBox(null);
    expect(box.maxX).toBeGreaterThan(box.minX);
    expect(box.maxY).toBeGreaterThan(box.minY);
  });
});

describe("computePreviewGeometry", () => {
  it("overlays layers at their true coordinates (no exploded offset)", () => {
    const g = computePreviewGeometry(braidLikeFixture(), CONFIG);
    // contentBox == footprintBox: layers share the same coordinates.
    expect(g.contentBox.minX).toBe(g.footprintBox.minX);
    expect(g.contentBox.minY).toBe(g.footprintBox.minY);
    expect(g.contentBox.maxX).toBe(g.footprintBox.maxX);
    expect(g.contentBox.maxY).toBe(g.footprintBox.maxY);
    expect(g.contentBox.maxY).toBeCloseTo(0.021, 9);
    expect(g.contentBox.minY).toBeCloseTo(0, 9);
  });

  it("places the magnet strip 1 mm above the tallest content", () => {
    const g = computePreviewGeometry(braidLikeFixture(), CONFIG);
    expect(g.magnetTop).toBeCloseTo(g.contentBox.maxY + 0.001, 9);
    expect(g.magnetSpan).toBeCloseTo(11 * 0.006 + 0.0045, 9);
    expect(g.fitBounds.maxY).toBeCloseTo(g.magnetTop + 0.003, 9);
    // The camera fit follows the painted solids, not the unused half-gap at
    // the right end of the configured pitch span.
    expect(g.fitBounds.maxX).toBeCloseTo(0.00075 + 11 * 0.006 + 0.0045, 9);
    // fit x must cover both the winding and the painted magnet bars
    expect(g.fitBounds.minX).toBeLessThanOrEqual(g.contentBox.minX);
    expect(g.fitBounds.maxX).toBeGreaterThanOrEqual(g.contentBox.maxX);
  });

  it("sizes the board panel 1.5 mm around the overlaid content", () => {
    const g = computePreviewGeometry(braidLikeFixture(), CONFIG);
    expect(g.boardRect.x).toBeCloseTo(g.contentBox.minX - 0.0015, 9);
    expect(g.boardRect.y).toBeCloseTo(g.contentBox.minY - 0.0015, 9);
    expect(g.boardRect.w).toBeCloseTo(g.contentBox.maxX - g.contentBox.minX + 0.003, 9);
    expect(g.boardRect.h).toBeCloseTo(g.contentBox.maxY - g.contentBox.minY + 0.003, 9);
  });

  it("reports only the layers actually present, not the configured total", () => {
    const g = computePreviewGeometry(braidLikeFixture(), CONFIG);
    expect(g.renderedLayerCount).toBe(2); // fixture config says layer_count 4
    const empty = computePreviewGeometry(null, CONFIG);
    expect(empty.renderedLayerCount).toBe(0);
  });
});

describe("computeMagnets", () => {
  it("centres solid bars inside their pitch cells when no sidecar is present", () => {
    const mags = computeMagnets(CONFIG);
    expect(mags).toHaveLength(12);
    // 4.5 mm bar in a 6 mm pitch cell: bar centre sits at half the pitch,
    // i.e. the bar starts at gap/2.
    expect(mags[0].x).toBeCloseTo(0.00075, 9);
    expect(mags[0].w).toBeCloseTo(0.0045, 9);
    expect(mags[0].pole).toBe(1);
    expect(mags[1].x).toBeCloseTo(0.00075 + 0.006, 9);
    expect(mags[1].w).toBeCloseTo(0.0045, 9);
    expect(mags[1].pole).toBe(-1);
    expect(mags[11].x).toBeCloseTo(0.00075 + 11 * 0.006, 9);
  });

  it("centres each magnet bar on a B-phase slot centre", () => {
    const dimensions: { pole_regions: PoleRegionDto[] } = {
      pole_regions: [
        // Phase bands mirror the infinity braid with a 6 mm pole pitch
        // (P_e/2): one region per phase per pole pitch, each phase
        // interleaved by pole_pitch / phases = 2 mm. Centres: A1=3, B1=5,
        // C1=7, A2=9, B2=11 mm.
        { phase: "A", pole_index: 0, start: [0, 0], end: [0.006, 0] },
        { phase: "B", pole_index: 0, start: [0.002, 0], end: [0.008, 0] },
        { phase: "C", pole_index: 0, start: [0.004, 0], end: [0.01, 0] },
        { phase: "A", pole_index: 1, start: [0.006, 0], end: [0.012, 0] },
        { phase: "B", pole_index: 1, start: [0.008, 0], end: [0.014, 0] },
      ],
    };
    const mags = computeMagnets(CONFIG, dimensions);

    // First bar is CENTRED on the neutral B1 slot centre (5 mm), so the
    // pole sits symmetrically inside its slot band.
    expect(mags[0].x).toBeCloseTo(0.005 - 0.0045 / 2, 9);
    expect(mags[0].x + mags[0].w / 2).toBeCloseTo(0.005, 9);
    expect(computeMagnetStartX(CONFIG, dimensions)).toBeCloseTo(0.005 - 0.0045 / 2, 9);

    // The second bar centre falls on the next B-phase centre (B2 = 11 mm).
    expect(mags[1].x).toBeCloseTo(0.005 + 0.006 - 0.0045 / 2, 9);
    expect(mags[1].x + mags[1].w / 2).toBeCloseTo(0.011, 9);

    // Without A2/B2, the available B1 neutral zone is still the anchor rather
    // than treating A1 as a substitute for the missing second-period zone.
    const onePeriod = {
      pole_regions: dimensions.pole_regions.filter((region) => region.pole_index === 0),
    };
    expect(computeMagnetStartX(CONFIG, onePeriod)).toBeCloseTo(0.005 - 0.0045 / 2, 9);
  });
});

describe("computeUniqueLayers", () => {
  it("lists distinct layer indices ascending", () => {
    const layers = computeUniqueLayers(braidLikeFixture());
    expect(layers.map((l) => l.idx)).toEqual([0, 1]);
  });

  it("returns [] with no coils", () => {
    expect(computeUniqueLayers(null)).toEqual([]);
  });
});

describe("computeUniquePhases", () => {
  it("dedupes per-(phase, layer) coils by phase_idx, sorted ascending", () => {
    const uniq = computeUniquePhases(braidLikeFixture());
    expect(uniq.map((u) => u.idx)).toEqual([0, 1, 2]);
    expect(uniq[0].name).toBe("A");
  });

  it("returns [] with no coils", () => {
    expect(computeUniquePhases(null)).toEqual([]);
  });
});

describe("computeMoverStripBounds", () => {
  const base = { minX: 0, minY: 0, maxX: 0.018, maxY: 0.033 };
  const magnets = [
    { x: -0.002, w: 0.01, pole: 1 },
    { x: 0.01, w: 0.01, pole: -1 },
  ];

  it("keeps the base without magnets and includes the strip at zero offset", () => {
    expect(computeMoverStripBounds(base, [], 0.02, 0.034, 0.003)).toEqual(base);
    const atRest = computeMoverStripBounds(base, magnets, 0, 0.034, 0.003);
    expect(atRest.minX).toBeCloseTo(-0.002, 9);
    expect(atRest.maxX).toBeCloseTo(0.02, 9);
    expect(atRest.maxY).toBeCloseTo(0.037, 9);
  });

  it("unions the strip translated to the far end of travel", () => {
    const b = computeMoverStripBounds(base, magnets, 0.075, 0.034, 0.003);
    // Strip at rest spans [-0.002, 0.02]; shifted +75 mm → [0.073, 0.095].
    expect(b.maxX).toBeCloseTo(0.095, 9);
    expect(b.maxY).toBeCloseTo(0.037, 9);
    // The base box still bounds the lower content.
    expect(b.minY).toBeCloseTo(base.minY, 9);
  });
});

describe("computeOverlayFitBounds", () => {
  const base = { minX: 0, minY: 0, maxX: 0.018, maxY: 0.033 };

  it("keeps the base box when there are no overlays", () => {
    expect(computeOverlayFitBounds(base, null, [])).toEqual(base);
  });

  it("expands the fit for the ruler floating above the magnet strip", () => {
    const ruler = computePolePitchRuler({ pole_pitch_m: 0.012 }, 0.005, 0.034);
    const bounds = computeOverlayFitBounds(base, ruler, []);
    expect(bounds.maxY).toBeGreaterThan(base.maxY); // ruler above the strip
    expect(bounds.maxX).toBeGreaterThanOrEqual(base.maxX);
    expect(bounds.minX).toBeLessThanOrEqual(base.minX);
  });

  it("covers band-row brackets that reach past the content box", () => {
    const row = {
      phaseIdx: 0,
      layer: 0,
      phaseName: "A",
      anchorX: 0.019,
      y: 0.012,
      bandM: 0.004,
      maxM: null,
      marginM: null,
      status: "no-limit" as const,
    };
    const bounds = computeOverlayFitBounds(base, null, [row]);
    expect(bounds.maxX).toBeGreaterThan(base.maxX);
  });

  it("expands the fit to cover pole-region zones poking past the nominal domain", () => {
    const zones = computePoleRegionZones({ pole_regions: [
      { phase: "A", pole_index: 0, start: [-0.004, 0.001], end: [0.008, 0.001] },
      { phase: "A", pole_index: 1, start: [0.008, 0.001], end: [0.02, 0.001] },
      { phase: "B", pole_index: 0, start: [0.005, 0.01], end: [0.017, 0.01] },
      { phase: "C", pole_index: 0, start: [0.012, 0.01], end: [0.009, 0.01] },
    ] });
    const zoneBox = computePoleRegionBounds(zones, 0.018, 0.02)!;
    expect(zoneBox).not.toBeNull();
    expect(zoneBox.minX).toBeLessThan(base.minX);
    expect(zoneBox.maxX).toBeGreaterThan(base.maxX);
    const bounds = computeOverlayFitBounds(base, null, [], zones, 0.018, 0.02);
    expect(bounds.minX).toBeLessThan(base.minX);
    expect(bounds.maxX).toBeGreaterThan(base.maxX);
    // Backward compatible: no zones → identical to the 3-arg call.
    expect(computeOverlayFitBounds(base, null, [])).toEqual(base);
  });
});

describe("traceExtentMetres", () => {
  it("measures the routed traces' first-to-last X span (the routing domain)", async () => {
    const { mockCoils } = await import("../ipc/mocks");
    const { ConfigStore } = await import("../stores/config.svelte");
    const config = new ConfigStore();
    const coils = mockCoils(config.toIpc());
    const span = traceExtentMetres(coils);
    expect(span).not.toBeNull();
    // Traces tile the routing domain, which equals the active area (no end
    // padding: 147 mm) — exactly config.trace_total_length_mm.
    expect((span![1] - span![0]) * 1000).toBeCloseTo(config.trace_total_length_mm, 3);
  });

  it("returns null without a coil payload", () => {
    expect(traceExtentMetres(null)).toBeNull();
  });
});

describe("measureTrace", () => {
  it("returns the measured trace length and start (mock spans the domain)", async () => {
    const { mockCoils } = await import("../ipc/mocks");
    const { ConfigStore } = await import("../stores/config.svelte");
    const config = new ConfigStore();
    const m = measureTrace(mockCoils(config.toIpc()), config);
    expect(m).not.toBeNull();
    expect(m!.traceLengthMm).toBeCloseTo(145.5, 3);
    expect(m!.traceStartMm).toBeCloseTo(0, 6);
  });

  it("is null without a payload", async () => {
    const { ConfigStore } = await import("../stores/config.svelte");
    expect(measureTrace(null, new ConfigStore())).toBeNull();
  });
});
