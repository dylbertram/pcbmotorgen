import type { TravelEnvelopeDto } from "../types";

/**
 * Fixed UI placeholder, not a configuration-derived travel envelope. These
 * reference values (12 magnets, 12 mm electrical period, 0–147 mm copper)
 * keep the preview usable until the native backend responds. They are not
 * valid for other configurations or a physical flush envelope. MotionStore
 * must surface its unavailable warning whenever this is active. Actual
 * envelope calculation belongs to the native travel_envelope command.
 */
export const PLACEHOLDER_TRAVEL_ENVELOPE: TravelEnvelopeDto = {
  min_position_m: 0.036,
  max_position_m: 0.111,
  rest_phase_m: 0.01,
  electrical_period_m: 0.012,
};

/** Native IPC returns a fresh object; the browser mock returns this instance. */
export function isPlaceholderEnvelope(dto: TravelEnvelopeDto | null | undefined): boolean {
  return dto === PLACEHOLDER_TRAVEL_ENVELOPE;
}
