import type { ForceSweepResult, LinearMotorConfig } from "../types";

// Browser-preview coefficients, not calibrated or qualified solver results.
const FORCE_BASELINE_K = 0.4;
const NORMAL_FORCE_K = 1.6;
const FORCE_RIPPLE_PCT = 0.08;

export function mockForceSweep(c: LinearMotorConfig): ForceSweepResult {
  const n = c.n_positions;
  const span = (c.magnet_count - 1) * c.magnet_pitch_m + c.magnet_width_m;
  const travel = Math.max(0, c.active_area_length_m - span);
  const positions = Array.from({ length: n }, (_, i) => c.magnet_width_m / 2 + (travel * i) / (n - 1));
  // Sinusoidal-ish force with ripple + a normal-force baseline.
  const br = c.magnet_remanence_t;
  const ipeak = c.max_current_a;
  const baseline = FORCE_BASELINE_K * br * ipeak * c.num_layers * (c.magnet_count / 10);
  const ripple = baseline * FORCE_RIPPLE_PCT;
  const force_x = positions.map(
    (x) => baseline + ripple * Math.sin((x / Math.max(c.magnet_pitch_m, 1e-6)) * 2 * Math.PI * c.phases),
  );
  const force_y = positions.map((_, idx) => 0.01 * Math.sin(idx));
  const force_z = positions.map(() => baseline * NORMAL_FORCE_K);
  const mean = force_x.reduce((a, b) => a + b, 0) / n;
  const peak = Math.max(...force_x);
  const min = Math.min(...force_x);
  const ripplePct = Math.abs(mean) < 1e-12 ? 0 : ((peak - min) / Math.abs(mean)) * 100;
  return {
    positions_m: positions,
    force_x_n: force_x,
    force_y_n: force_y,
    force_z_n: force_z,
    per_phase_force_x: force_x.map((f) => [f / c.phases, f / c.phases, f / c.phases]),
    commutation: c.commutation,
    current_a: ipeak,
    mean_thrust_n: mean,
    peak_thrust_n: peak,
    min_thrust_n: min,
    ripple_pct: ripplePct,
    n_positions: n,
  };
}
