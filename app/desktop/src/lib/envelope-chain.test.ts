import { describe, expect, it } from "vitest";
import { fetchTravelEnvelope } from "./ipc";
import {
  PLACEHOLDER_TRAVEL_ENVELOPE,
  isPlaceholderEnvelope,
} from "./ipc/mocks";
import { ConfigStore } from "./stores/config.svelte";
import { MotionStore } from "./stores/motion.svelte";

describe("envelope consumption chain", () => {
  // PLACEHOLDER REFERENCE PINS (kata ab30) — the mock IPC returns the shared
  // fixed placeholder, whose numbers are the pinned output of the authority
  // (crates/pcbmotorgen-simulation `equilibrium::travel_envelope_over_slots`,
  // kata 5c7r) for the reference build N=12, P_e=12 mm, copper [0, 147] mm.
  // If these numbers move, the placeholder literal was edited and the
  // dev-mode screenshots shift with it.
  it("placeholder mock envelope drives MotionStore bounds and keeps the warning visible", async () => {
    const config = new ConfigStore();
    const ipc = config.toIpc();
    const env = await fetchTravelEnvelope(ipc);
    // The mock is a fixed literal, NOT computed: it IS the shared constant.
    expect(isPlaceholderEnvelope(env)).toBe(true);
    expect(env).toBe(PLACEHOLDER_TRAVEL_ENVELOPE);
    expect(env.min_position_m).toBeCloseTo(0.036, 10);
    expect(env.max_position_m).toBeCloseTo(0.111, 10);
    expect(env.rest_phase_m).toBeCloseTo(0.01, 10);
    expect(env.electrical_period_m).toBeCloseTo(0.012, 10);

    const motion = new MotionStore(config);
    // Before any envelope: placeholder bounds (36/111 mm) + warning raised.
    expect(motion.moverMinMm).toBeCloseTo(36, 3);
    expect(motion.moverMaxMm).toBeCloseTo(111, 3);
    expect(motion.envelopeWarning).not.toBeNull();
    expect(motion.envelopeWarning?.message).toContain(
      "Travel envelope unavailable — backend required",
    );

    motion.setEnvelope(env);
    // The placeholder IS what the mock returned, so the warning STAYS
    // visible — placeholder numbers are never presented as real physics.
    expect(motion.envelopeWarning).not.toBeNull();
    expect(motion.moverMinMm).toBeCloseTo(36, 3);
    expect(motion.moverMaxMm).toBeCloseTo(111, 3);
    expect(motion.restPhaseMm).toBeCloseTo(10, 3);
    expect(motion.electricalPeriodMm).toBeCloseTo(12, 3);

    // The fixed legacy placeholder uses pitch-cell limits. Physical bars
    // exclude the extra inter-magnet gap, so it is not a flush envelope.
    motion.commit(motion.moverMinMm);
    expect(motion.stripStartMm).toBeCloseTo(0.75, 6);
    expect(motion.stripEndMm).toBeCloseTo(71.25, 6);

    // Keep the placeholder warning: these limits are not configuration-derived.
    motion.commit(motion.moverMaxMm);
    expect(motion.stripStartMm).toBeCloseTo(75.75, 6);
    expect(motion.stripEndMm).toBeCloseTo(146.25, 6);
  });

  it("rejects implausible envelopes (mm reported as metres) and keeps the flagged placeholder", async () => {
    const config = new ConfigStore();
    const motion = new MotionStore(config);
    // The regression from the measured-track unit bug: a 203 554 mm track
    // shipped as metres → slider max ≈ 203 554 mm. Must be rejected.
    motion.setEnvelope({
      min_position_m: 0.022,
      max_position_m: 190.0,
      rest_phase_m: 0.01,
      electrical_period_m: 0.012,
    });
    expect(motion.envelope).toBeNull();
    // Rejection is NOT silent (kata ab30): the placeholder stays active and
    // the "travel envelope unavailable" warning remains raised.
    expect(motion.usingPlaceholderEnvelope).toBe(true);
    expect(motion.envelopeWarning).not.toBeNull();
    expect(motion.moverMinMm).toBeCloseTo(36, 3);

    // A plausible, non-placeholder envelope installs and CLEARS the warning:
    // the bounds now come from the backend value alone.
    motion.setEnvelope({
      min_position_m: 0.04,
      max_position_m: 0.1,
      rest_phase_m: 0.01,
      electrical_period_m: 0.012,
    });
    expect(motion.envelope).not.toBeNull();
    expect(motion.usingPlaceholderEnvelope).toBe(false);
    expect(motion.envelopeWarning).toBeNull();
    expect(motion.moverMinMm).toBeCloseTo(40, 3);
    expect(motion.moverMaxMm).toBeCloseTo(100, 3);
    expect(motion.restPhaseMm).toBeCloseTo(10, 3);
  });

  it("installs the charge-based backend envelope (kata k5r5) and drives every consumer bound", async () => {
    // MEASURED live-backend output (commands/physics.rs
    // `command_refines_the_max_endpoint_on_app_defaults`): on the app-default
    // design the charge refinement pulls the max endpoint INWARD off the
    // 111 mm flush limit — edge-anchored on the phase owning the braid's
    // last active leg (C), the mirrored min-state charges. The placeholder
    // pin [36, 111] is dev-mock only.
    const config = new ConfigStore();
    const motion = new MotionStore(config);
    motion.setEnvelope({
      min_position_m: 0.036,
      max_position_m: 0.107_973,
      rest_phase_m: 0.01,
      electrical_period_m: 0.012,
    });
    expect(motion.usingPlaceholderEnvelope).toBe(false);
    expect(motion.envelopeWarning).toBeNull();

    // Position slider endpoints (MoverPositionControls) and the design
    // reflection both read these:
    expect(motion.moverMinMm).toBeCloseTo(36, 3);
    expect(motion.moverMaxMm).toBeCloseTo(107.973, 3);

    // The refined max is NOT a stable rest (off the φ = 10 mm, P_e = 12 mm
    // lattice) — the mover may hold between rests; endpoints are limits.
    motion.commit(motion.moverMaxMm);
    expect(motion.stripStartMm).toBeCloseTo(72.723, 3);
    expect(motion.stripEndMm).toBeCloseTo(143.223, 3);
    expect(motion.offsetFromRestMm).toBeCloseTo(71.973, 3);

    // HoldingForceChart domain spans [min, max]; zeros stay on the lattice.
    const domainEnd = Math.max(motion.moverMinMm + 1e-6, motion.moverMaxMm);
    expect(domainEnd).toBeCloseTo(107.973, 3);
  });
});
