/**
 * Shared mover-position state for the design reflection.
 *
 * Owned by App.svelte and passed to both the TravelDiagram (position slider /
 * iso view) and the CoilPreview (magnet strip shading), so dragging the
 * position in one place moves the magnet overlay in the other.
 *
 * The value is the CENTER of the magnet array in ABSOLUTE TRACK coordinates
 * (the routing/domain frame: the copper active area is
 * [0, active_area_length_m], no padding offset) — the same frame every
 * preview draws in. Motion input is continuous: a coreless motor has no
 * detent/cogging force.
 *
 * Travel envelope (kata ab30): the RANGE endpoints and the rest phase come
 * EXCLUSIVELY from the backend — the `travel_envelope` Tauri command backed
 * by `pcbmotorgen_simulation::equilibrium::charge::travel_envelope_charge_based`
 * (charge-based endpoints clamped into the span-aware flush limits, kata
 * k5r5 + 5c7r). This store does NOT re-derive that
 * math. Until a plausible envelope is installed — and whenever the
 * browser-dev placeholder mock is active — the bounds come from the shared
 * fixed PLACEHOLDER_TRAVEL_ENVELOPE (lib/ipc/mocks.ts) and the
 * "travel envelope unavailable — backend required" warning is raised via
 * `envelopeWarning`, so placeholder numbers are never mistaken for real
 * physics.
 */

import type { ConfigStore } from "./config.svelte";
import type { TravelEnvelopeDto } from "../types";
import type { Finding } from "../validation";
import {
  PLACEHOLDER_TRAVEL_ENVELOPE,
  isPlaceholderEnvelope,
} from "../ipc/mocks";

/** The validation warning raised while only the placeholder envelope is
 *  active. The message text is the kata ab30 contract — keep the wording. */
const ENVELOPE_PLACEHOLDER_WARNING: Finding = {
  id: "travel-envelope-unavailable",
  level: "warning",
  message:
    "Travel envelope unavailable — backend required. Showing the fixed " +
    "placeholder envelope (reference pin 36–111 mm), which is not " +
    "derived from this configuration.",
};

export class MotionStore {
  /** Raw mover-centre input (mm) before clamping. */
  positionMm = $state(60);

  /**
   * Envelope installed from the backend (SI metres); null until a plausible
   * one arrives. Null ⇒ the shared placeholder is active and
   * `envelopeWarning` is raised.
   */
  envelope = $state.raw<TravelEnvelopeDto | null>(null);

  constructor(private config: ConfigStore) { }

  moverSpanMm = $derived.by(() => this.config.mover_span_mm);

  /**
   * Electrical period P_e (mm): one full 360° cycle = 2 pole pitches.
   * P_e is a user INPUT echoed back by the envelope, so the config remains
   * its source — this is not envelope math re-derivation.
   */
  electricalPeriodMm = $derived.by(() => this.config.pole_pitch_mm * 2);

  /**
   * The envelope currently driving the bounds: the backend value when one is
   * installed, otherwise the shared fixed placeholder (lib/ipc/mocks.ts;
   * authority: `equilibrium::travel_envelope_over_slots`). Never re-computed
   * from config — that duplication was removed by kata ab30.
   */
  activeEnvelope = $derived.by(
    () => this.envelope ?? PLACEHOLDER_TRAVEL_ENVELOPE,
  );

  /**
   * Rest phase φ (mm): stable rest centres satisfy x ≡ φ (mod P_e).
   * Comes from the backend envelope, or the flagged placeholder while none
   * is installed.
   */
  restPhaseMm = $derived(this.activeEnvelope.rest_phase_m * 1000);

  /**
   * Leftmost allowed mover centre (mm) — from the backend envelope, or the
   * flagged placeholder. A mechanical limit, not a stable rest position.
   */
  moverMinMm = $derived(this.activeEnvelope.min_position_m * 1000);

  /**
   * Rightmost allowed mover centre (mm). The backend never inverts the
   * envelope (on a degenerate copper region max clamps to min); the
   * Math.max guard only preserves that ordering defensively — it derives no
   * geometry.
   */
  moverMaxMm = $derived.by(() =>
    Math.max(this.moverMinMm, this.activeEnvelope.max_position_m * 1000),
  );

  /**
   * True while the active bounds are the placeholder rather than a plausible
   * backend envelope — before the first envelope arrives, after a
   * sanity-gate rejection, and whenever the browser-dev mock (which returns
   * the shared placeholder constant) is the source.
   */
  usingPlaceholderEnvelope = $derived(
    this.envelope === null || isPlaceholderEnvelope(this.envelope),
  );

  /**
   * The validation warning to surface (or null): raised exactly while the
   * placeholder envelope drives the bounds, so placeholder numbers are
   * never silently presented as real physics.
   */
  envelopeWarning = $derived<Finding | null>(
    this.usingPlaceholderEnvelope ? ENVELOPE_PLACEHOLDER_WARNING : null,
  );

  /** Clamped mover centre; all consumers read this. */
  clampedPositionMm = $derived(
    Number.isFinite(this.positionMm)
      ? Math.max(this.moverMinMm, Math.min(this.moverMaxMm, this.positionMm))
      : this.moverMinMm,
  );
  /** Strip shift from the leftmost limit (mm): 0 at moverMinMm. */
  offsetFromRestMm = $derived(this.clampedPositionMm - this.moverMinMm);

  /**
   * Mover strip extent (mm) in the DOMAIN frame — centred on the current
   * position, so the drawn edges always equal position ± mover_span/2 and
   * match every printed number exactly.
   */
  stripStartMm = $derived(this.clampedPositionMm - this.moverSpanMm / 2);
  stripEndMm = $derived(this.clampedPositionMm + this.moverSpanMm / 2);

  /** Commit a raw position (slider or number field) into the store. */
  commit(value: number): void {
    if (!Number.isFinite(value)) return;
    this.positionMm = value;
  }

  /**
   * Install a fetched backend envelope (SI metres → internal mm).
   *
   * Sanity-gated: positions must be plausible coordinates ON this board
   * (finite, ordered, non-negative, and no farther than the routing domain
   * plus 1% slack). A backend unit slip — e.g. millimetre geometry reported
   * as metres — would otherwise blow the slider up to ~200 000 mm and shrink
   * the CoilPreview camera to a speck. On rejection the envelope is NOT
   * installed: the placeholder stays active and `envelopeWarning` remains
   * raised, so the situation is disclosed instead of silently substituted
   * (kata ab30 — there is no TS re-derivation to fall back to any more).
   */
  setEnvelope(dto: TravelEnvelopeDto): void {
    const minMm = dto.min_position_m * 1000;
    const maxMm = dto.max_position_m * 1000;
    const domainMm = this.config.trace_total_length_mm;
    const plausible =
      Number.isFinite(minMm) &&
      Number.isFinite(maxMm) &&
      minMm >= 0 &&
      maxMm >= minMm &&
      maxMm <= domainMm * 1.01;
    if (!plausible) return;
    this.envelope = dto;
  }
}
