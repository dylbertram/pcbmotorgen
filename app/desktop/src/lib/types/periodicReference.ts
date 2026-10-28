/** Explicit periodic static reference; never a finite-motor operating result. */
export interface PeriodicStaticRun {
  depth_cells: number;
  odd_modes: number;
  angular_samples: number;
  newton_iterations: number;
  relative_gradient_residual: number;
  field_ratio_at_pm_centre_pcb_top: number;
  mean_pressure_over_magnet_width_pa: number;
  reflected_normal_modes_t: number[];
  quadrature_sampled_peak_b_t: number;
  quadrature_saturated_fraction: number;
  isolated_sheet_dc_factors_per_alignment: [number, number];
  differential_relative_residual: number;
}

export interface PeriodicStaticReference {
  scope: string;
  magnetic_thickness_m: number;
  mu_initial: number;
  saturation_polarization_t: number;
  elapsed_seconds: number;
  runs: PeriodicStaticRun[];
  max_field_refinement_change: number;
  max_pressure_refinement_change: number;
  max_dc_factor_absolute_refinement_change: number;
  warnings: string[];
}
