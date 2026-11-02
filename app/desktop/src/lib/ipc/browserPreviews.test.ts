/**
 * Browser-preview DTO checks. Values are fixtures, not solver results.
 */

import { describe, expect, it } from "vitest";
import { mockCoils } from "./coilPreviewMock";
import { mockHeightStack } from "./heightStackMock";
import { mockForceSweep } from "./forceSweepMock";
import { fetchMagnetGrades, fetchTravelEnvelope } from "./physics";
import { PLACEHOLDER_TRAVEL_ENVELOPE, isPlaceholderEnvelope } from "../simulation/travelEnvelopePlaceholder";
import type { LinearMotorConfig } from "../types";
import { computeFootprintBox, computeMagnets } from "../preview/previewGeometry";

it("force sweep endpoints keep the physical array inside the active area", () => {
  for (const width of [0.006, 0.012]) {
    const c = makeConfig({ magnet_width_m: width, spacing_ratio: 0.8 });
    const sweep = mockForceSweep(c);
    const first = sweep.positions_m[0];
    const last = sweep.positions_m[sweep.positions_m.length - 1];
    expect(first - width / 2).toBeCloseTo(0, 12);
    expect(last + (c.magnet_count - 1) * c.magnet_pitch_m + width / 2)
      .toBeCloseTo(c.active_area_length_m, 12);
  }
});

function makeConfig(overrides: Partial<LinearMotorConfig> = {}): LinearMotorConfig {
  return {
    active_area_length_m: 0.195,
    board_width_m: 0.02,
    pcb_thickness_m: 0.0016,
    strands_per_phase: 2,
    magnet_count: 10,
    magnet_width_m: 0.01,
    magnet_cross_width_m: 0.01,
    magnet_height_m: 0.004,
    magnet_gap_m: 0.002,
    magnet_pitch_m: 0.012,
    magnet_remanence_t: 1.34,
    magnet_grade: "N44",
    air_gap_m: 0.0005,
    routing_pattern: "infinity-braid",
    routing_params: {},
    phases: 3,
    spacing_ratio: 1,
    max_current_a: 1.0,
    supply_voltage_v: 5.0,
    num_layers: 4,
    min_trace_m: 0.000127,
    trace_width_m: 0.000127,
    min_space_m: 0.000127,
    min_via_drill_m: 0.0002,
    min_via_annular_ring_m: 0.0001,
    max_layers: 12,
    drive_frequency_hz: 500,
    max_temperature_rise_c: 20,
    target_force_n: 0.5,
    peak_force_n: 1.0,
    friction_n: 0.05,
    carriage_mass_kg: 0.015,
    max_accel_m_s2: 2.0,
    capacitor_bank_uf: 1000,
    commutation: "max_thrust",
    n_positions: 50,
    meshing: 20,
    backplane: null,
    name: null,
    ...overrides,
  };
}

describe("browser magnet grades", () => {
  it("mirrors the static TS grade catalog in wire shape", async () => {
    const grades = await fetchMagnetGrades();
    expect(grades.length).toBeGreaterThanOrEqual(6);
    for (const g of grades) {
      expect(typeof g.name).toBe("string");
      expect(g.br_min_t).toBeLessThanOrEqual(g.br_typ_t);
      expect(g.br_typ_t).toBeLessThanOrEqual(g.br_max_t);
      expect(Object.keys(g.max_temp_c).length).toBeGreaterThan(0);
    }
  });
});

describe("mockCoils", () => {
  it("produces one coil per (phase × layer) with active + end-turn segments", () => {
    const c = makeConfig();
    const coils = mockCoils(c);
    // One coil per (phase, layer) pair — the preview must render every
    // layer, mirroring the real backend's multi-layer output.
    expect(coils.phases).toHaveLength(c.phases * c.num_layers);
    expect(coils.layer_count).toBe(c.num_layers);
    const layerIdxMax = Math.max(...coils.phases.map((p) => p.layer_idx));
    expect(layerIdxMax).toBe(c.num_layers - 1);
    const phaseIdxMax = Math.max(...coils.phases.map((p) => p.phase_idx));
    expect(phaseIdxMax).toBe(c.phases - 1);
    for (const ph of coils.phases) {
      expect(ph.phase_idx).toBeGreaterThanOrEqual(0);
      expect(ph.segments.length).toBeGreaterThan(0);
      const actives = ph.segments.filter((s) => s.is_active);
      expect(actives.length).toBeGreaterThan(0);
      expect(ph.active_conductor_count).toBe(actives.length);
    }
  });

  it("emits representative pole regions (one per phase per pole pitch)", () => {
    const c = makeConfig(); // active_area 0.195, pitch 0.012
    const regions = mockCoils(c).routing_dimensions!.pole_regions;
    expect(regions.length).toBeGreaterThan(0);
    // Mirrors the infinity braid: regions tile the routing domain — which
    // EQUALS the active area (no end padding) — one per phase per pole pitch.
    const regionsPerPhase = Math.floor(
      c.active_area_length_m / c.magnet_pitch_m,
    );
    expect(regionsPerPhase).toBeGreaterThan(0);
    expect(regions).toHaveLength(regionsPerPhase * c.phases);
    const labels = new Set(regions.map((r) => r.phase));
    expect(labels).toEqual(new Set(["A", "B", "C"]));
    for (const r of regions) {
      expect(["A", "B", "C"]).toContain(r.phase);
      expect(r.pole_index).toBeGreaterThanOrEqual(0);
      for (const coord of [r.start[0], r.start[1], r.end[0], r.end[1]]) {
        expect(Number.isFinite(coord)).toBe(true);
      }
      // metre coordinates with a strictly positive width
      expect(r.end[0] - r.start[0]).toBeGreaterThan(0);
    }
  });

  it("routes mock coils across the FULL domain so the mover stays over conductors for its whole travel", async () => {
    // Default-style mover: P_e 12 mm → pole pitch 6 mm, 12 poles, k 0.75.
    const c = makeConfig({
      magnet_count: 12,
      magnet_pitch_m: 0.006,
      magnet_width_m: 0.0045,
      magnet_gap_m: 0.0015,
      active_area_length_m: 0.147,
    });
    const coils = mockCoils(c);
    const footprint = computeFootprintBox(coils);
    // Traces (and the board panel) span the routing domain, which EQUALS the
    // active area (no end padding) — the mover must have coils beneath it at
    // every travel position, exactly like the real infinity braid.
    expect(footprint.maxX).toBeCloseTo(0.147, 9);

    const magnets = computeMagnets(
      { magnet_count: 12, magnet_width_mm: 4.5, magnet_gap_mm: 1.5 },
      coils.routing_dimensions,
    );
    const travelM = 0.075;
    const restMin = magnets[0].x;
    const restMax = magnets[magnets.length - 1].x + 4.5 / 1000;
    // The painted bars span eleven pitches plus one magnet width, leaving
    // one gap of slack relative to twelve full pitch cells plus travel.
    expect(restMax - restMin + travelM).toBeCloseTo(0.1455, 9);
    expect(footprint.maxX - (restMax - restMin + travelM)).toBeCloseTo(0.0015, 9);
    // The drawn (pattern-anchored) rest strip starts on the board.
    expect(restMin).toBeGreaterThanOrEqual(0);
    // The mock travel envelope keeps the swept strip inside the domain.
    const env = await fetchTravelEnvelope(c);
    const spanM = restMax - restMin;
    const stripStartAtMin = env.min_position_m - spanM / 2;
    const stripEndAtMax = env.max_position_m + spanM / 2;
    expect(stripStartAtMin).toBeGreaterThanOrEqual(0);
    expect(stripEndAtMax).toBeLessThanOrEqual(footprint.maxX);
  });
});

describe("mockCoils per-slot metrics", () => {
  it("reports the pinned braid reference values for the infinity braid", () => {
    const c = makeConfig();
    const d = mockCoils(c).routing_dimensions!;
    expect(d.slot_count).toBe(975);
    expect(d.slot_pitch_m).toBeCloseTo(6.1538e-4, 12);
    expect(d.interleave_step_m).toBeCloseTo(8.0e-4, 12);
    // A slot houses ONE active leg: the per-band slot width is distinct from
    // (and much smaller than) the whole-bundle band width.
    expect(d.phase_band_widths.length).toBeGreaterThan(0);
    for (const band of d.phase_band_widths) {
      expect(band.slot_width_m).toBeCloseTo(1.1662e-4, 12);
      expect(band.slot_width_m!).toBeLessThan(band.band_width_m);
    }
  });

  it("leaves pattern-declared slot metrics null without a leg grid", () => {
    const c = makeConfig({ routing_pattern: "serpentine" });
    const d = mockCoils(c).routing_dimensions!;
    expect(d.slot_count).toBeNull();
    expect(d.slot_pitch_m).toBeNull();
    expect(d.interleave_step_m).toBeNull();
    // Per-band slot width is trace-geometry derived, not leg-grid derived.
    expect(d.phase_band_widths[0].slot_width_m).not.toBeNull();
  });
});

describe("mockForceSweep", () => {
  it("returns arrays sized to n_positions with a sensible mean/peak ordering", () => {
    const c = makeConfig({ n_positions: 25 });
    const s = mockForceSweep(c);
    expect(s.positions_m).toHaveLength(25);
    expect(s.force_x_n).toHaveLength(25);
    expect(s.force_z_n).toHaveLength(25);
    expect(s.n_positions).toBe(25);
    expect(s.min_thrust_n).toBeLessThanOrEqual(s.mean_thrust_n);
    expect(s.mean_thrust_n).toBeLessThanOrEqual(s.peak_thrust_n);
    expect(s.per_phase_force_x).toHaveLength(25);
    expect(s.per_phase_force_x[0]).toHaveLength(c.phases);
  });
});

describe("mockHeightStack", () => {
  it("does not add copper twice to an explicit stackup", () => {
    const h = mockHeightStack(makeConfig({ pcb_thickness_m:.0008, pcb_stackup:{copper_m:[35e-6,35e-6],dielectric_m:[.00073]} }));
    expect(h.cu_protrusion_m).toBe(0);
    expect(h.total_height_m).toBeCloseTo(h.pcb_thickness_m+h.solder_mask_m+h.air_gap_m+h.magnet_height_m+h.tolerance_m, 12);
  });
  it("sums the full stack including tolerance", () => {
    const c = makeConfig();
    const h = mockHeightStack(c);
    expect(h.total_height_m).toBeCloseTo(
      h.pcb_thickness_m + h.cu_protrusion_m + h.solder_mask_m + h.air_gap_m +
        h.magnet_height_m + h.tolerance_m + h.backplane_m + h.housing_gap_m + h.housing_m, 12,
    );
  });

  it("adds backplane layers, housing gap and housing to the total", () => {
    const bare = mockHeightStack(makeConfig());
    const h = mockHeightStack(makeConfig({
      backplane: {
        layers: [
          { material: "fr4", thickness_m: 0.0016 },
          { material: "mn_zn_ferrite", thickness_m: 0.002 },
        ],
        housing: { material: "aluminum6061", thickness_m: 0.003, gap_m: 0.001 },
      },
    }));
    expect(h.backplane_m).toBeCloseTo(0.0036, 12);
    expect(h.housing_gap_m).toBeCloseTo(0.001, 12);
    expect(h.housing_m).toBeCloseTo(0.003, 12);
    expect(h.total_height_m).toBeCloseTo(bare.total_height_m + 0.0036 + 0.001 + 0.003, 12);
    expect(h.backplane_analysis).toBeNull();
  });

  it("reports zero backplane heights when no backplane is configured", () => {
    const h = mockHeightStack(makeConfig());
    expect(h.backplane_m).toBe(0);
    expect(h.housing_gap_m).toBe(0);
    expect(h.housing_m).toBe(0);
  });
});

describe("browser travel envelope", () => {
  // PLACEHOLDER PINS (kata ab30) — the mock no longer re-derives the
  // envelope. It returns the shared fixed literal
  // (PLACEHOLDER_TRAVEL_ENVELOPE), whose numbers are the pinned output of
  // the authority (`equilibrium::travel_envelope_over_slots`, kata 5c7r)
  // for the reference build N=12, P_e=12 mm, copper [0, 147] mm.
  it("returns the shared placeholder constant (identity, config-independent)", async () => {
    const a = await fetchTravelEnvelope(
      makeConfig({ magnet_count: 12, magnet_pitch_m: 0.006, active_area_length_m: 0.147 }),
    );
    const b = await fetchTravelEnvelope(
      makeConfig({ magnet_count: 4, magnet_pitch_m: 0.024, active_area_length_m: 0.5 }),
    );
    expect(a).toBe(PLACEHOLDER_TRAVEL_ENVELOPE);
    expect(b).toBe(a);
    expect(isPlaceholderEnvelope(a)).toBe(true);
  });

  it("placeholder values stay the pinned reference: 36 → 111 mm, φ = 10 mm, P_e = 12 mm", async () => {
    const env = await fetchTravelEnvelope(makeConfig());
    expect(env.electrical_period_m).toBeCloseTo(0.012, 12);
    expect(env.min_position_m).toBeCloseTo(0.036, 12);
    expect(env.max_position_m).toBeCloseTo(0.111, 12);
    expect(env.rest_phase_m).toBeCloseTo(0.010, 12);
  });
});
