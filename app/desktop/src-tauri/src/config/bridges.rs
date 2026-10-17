//! Bridge methods on [`LinearMotorConfig`](super::LinearMotorConfig): sync
//! magnet grade, and conversion to the leaf crates (`RoutingContext`,
//! `DesignRules`, `SimulationInput`, `PhaseCoil`s, routing-pattern id).

use super::LinearMotorConfig;

// The following methods form the config API. In the binary these are partly
// exercised via `cargo test` (inline `#[cfg(test)]`) while the shipped runtime
// path builds the config straight from the IPC DTO's `to_core()`, so keep the
// API available without dead-code noise in release builds.
#[allow(dead_code)]
impl LinearMotorConfig {
    /// Sync `magnet_remanence_t` from `magnet_grade` unless Custom.
    pub fn sync_magnet_grade(&mut self) {
        if self.magnet_grade == pcbmotorgen_simulation::magnet_grades::CUSTOM_GRADE {
            return;
        }
        if let Some(br) = pcbmotorgen_simulation::magnet_grades::get_remanence(&self.magnet_grade) {
            self.magnet_remanence_t = br;
        }
    }

    /// Build a `RoutingContext` snapshot for the current config.
    ///
    /// The parent config remains SI/metres; the routing crate's public
    /// contract is millimetres, so this is the unit-conversion boundary.
    pub fn routing_context(&self) -> pcbmotorgen_routing::RoutingContext {
        pcbmotorgen_routing::RoutingContext {
            active_area_length_mm: self.active_area_length_m * 1e3,
            board_width_mm: self.board_width_m * 1e3,
            num_layers: self.num_layers.max(1),
            phases: self.phases.max(1),
            min_trace_mm: self.min_trace_m * 1e3,
            trace_width_mm: self.trace_width_m * 1e3,
            min_space_mm: self.min_space_m * 1e3,
            expects_continuous: false,
            params: self.routing_params.clone(),
            // Magnet layout: lets patterns align their repeating unit to the
            // pole pitch so the traces regenerate when the magnets change.
            magnet_pitch_mm: Some(self.magnet_pitch_m * 1e3),
            magnet_array_span_mm: Some(self.magnet_array_span_m() * 1e3),
            // No config field maps to an explicit inter-phase clearance yet;
            // `None` keeps the documented `min_space_mm` fallback (do not
            // invent UI config here).
            phase_clearance_mm: None,
        }
    }

    /// Build a `DesignRules` DFM snapshot for the current config. DesignRules
    /// are millimetres and owned by the DFM crate (pcbmotorgen-dfm, kata 0rgs);
    /// this bridge mirrors the config's copper sizing into it.
    pub fn design_rules(&self) -> pcbmotorgen_dfm::DesignRules {
        pcbmotorgen_dfm::DesignRules {
            min_trace_mm: self.min_trace_m * 1e3,
            trace_width_mm: self.trace_width_m * 1e3,
            min_space_mm: self.min_space_m * 1e3,
            min_via_drill_mm: self.min_via_drill_m * 1e3,
            min_via_annular_ring_mm: self.min_via_annular_ring_m * 1e3,
        }
    }

    /// Map the config verbatim onto a `SimulationInput` (single source of
    /// truth for all physics/derived arithmetic lives in the simulation crate).
    pub fn to_simulation(&self) -> pcbmotorgen_simulation::SimulationInput {
        pcbmotorgen_simulation::SimulationInput {
            magnet_dims_m: self.magnet_dims_m,
            magnet_count: self.magnet_count,
            magnet_pitch_m: self.magnet_pitch_m,
            magnet_remanence_t: self.magnet_remanence_t,
            active_area_length_m: self.active_area_length_m,
            board_width_m: self.board_width_m,
            pcb_thickness_m: self.pcb_thickness_m,
            air_gap_m: self.air_gap_m,
            strands_per_phase: self.strands_per_phase,
            phases: self.phases,
            spacing_ratio: self.spacing_ratio,
            max_current_a: self.max_current_a,
            supply_voltage_v: self.supply_voltage_v,
            // The simulation treats `min_trace_m` as the conductor width for
            // resistance and ampacity, so hand it the nominal (actual) width;
            // the design-rule floor lives in `DesignRules.min_trace_mm`.
            min_trace_m: self.trace_width_m,
            min_space_m: self.min_space_m,
            min_via_drill_m: self.min_via_drill_m,
            min_via_annular_ring_m: self.min_via_annular_ring_m,
            max_layers: self.max_layers,
            num_layers: self.num_layers,
            drive_frequency_hz: self.drive_frequency_hz,
            max_temperature_rise_c: self.max_temperature_rise_c,
            target_force_n: self.target_force_n,
            peak_force_n: self.peak_force_n,
            friction_n: self.friction_n,
            carriage_mass_kg: self.carriage_mass_kg,
            max_accel_m_s2: self.max_accel_m_s2,
            capacitor_bank_uf: self.capacitor_bank_uf,
            // No config field maps to declared phase bands yet; empty keeps
            // the analytic commutation offsets (kata hzs2 fallback).
            phase_bands: Vec::new(),
            backplane: self.backplane.clone(),
        }
    }

    /// Generate validated `PhaseCoil`s for the selected routing pattern.
    pub fn generate_coils_for_board(&self) -> Vec<pcbmotorgen_routing::PhaseCoil> {
        let id = self.routing_pattern_id();
        pcbmotorgen_routing::generate_coils_from_context(&self.routing_context(), &id)
    }

    /// The resolved routing-pattern id (defaults to `infinity-braid` when blank).
    pub fn routing_pattern_id(&self) -> String {
        let trimmed = self.routing_pattern.trim();
        if trimmed.is_empty() {
            "infinity-braid".to_string()
        } else {
            trimmed.to_string()
        }
    }
}

// ---------------------------------------------------------------------------
// Tests — magnet grade sync
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sync_magnet_grade_n44() {
        let mut cfg = LinearMotorConfig {
            magnet_grade: "N44".into(),
            magnet_remanence_t: 0.0,
            ..LinearMotorConfig::default()
        };
        cfg.sync_magnet_grade();
        assert!((cfg.magnet_remanence_t - 1.34).abs() < 1e-6);
    }

    #[test]
    fn test_sync_magnet_grade_n44h_suffix() {
        let mut cfg = LinearMotorConfig {
            magnet_grade: "N44H".into(),
            magnet_remanence_t: 0.0,
            ..LinearMotorConfig::default()
        };
        cfg.sync_magnet_grade();
        assert!((cfg.magnet_remanence_t - 1.34).abs() < 1e-6);
    }

    #[test]
    fn test_sync_magnet_grade_custom_unchanged() {
        let mut cfg = LinearMotorConfig {
            magnet_grade: "Custom".into(),
            magnet_remanence_t: 1.50,
            ..LinearMotorConfig::default()
        };
        cfg.sync_magnet_grade();
        assert!((cfg.magnet_remanence_t - 1.50).abs() < 1e-6);
    }
}
