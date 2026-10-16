//! Flat snapshot of board dimensions + DFM trace/space limits + phase count
//! handed to every routing pattern.
//!
//! Patterns must not depend on the concrete physics-core `LinearMotorConfig`,
//! keeping this crate decoupled. Pattern-specific knobs ride in [`params`].
//!
//! Every length in this context is millimetres. The parent application converts
//! its SI/metre config at the routing boundary.
//!
//! The `min_trace_mm` / `min_space_mm` / `phase_clearance_mm` fields are part
//! of this wire contract — patterns consume them for layout and phase-band
//! math. The DFM sizing/DRC authority itself lives downstream in the
//! `pcbmotorgen-dfm` crate (`DesignRules` + `check_interference`, kata 0rgs);
//! the application bridges the same config values into a `DesignRules`
//! snapshot for it.

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

/// Everything a routing pattern may need to produce geometry.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct RoutingContext {
    /// Physical length of the stator copper region [mm] (primary input).
    pub active_area_length_mm: f64,
    /// PCB dimension perpendicular to travel [mm].
    pub board_width_mm: f64,
    /// Number of copper layers in the stack.
    pub num_layers: u32,
    /// Number of electrical phases.
    pub phases: u32,
    /// Minimum manufacturable trace width [mm] — the design-rule floor.
    pub min_trace_mm: f64,
    /// Nominal (actual) copper trace width [mm]. Patterns lay out conductor
    /// geometry from this; `min_trace_mm` stays the floor. Zero means unset —
    /// [`RoutingContext::trace_width`] then falls back to `min_trace_mm`, so
    /// contexts serialized before this field existed keep their behaviour.
    #[serde(default)]
    pub trace_width_mm: f64,
    /// Minimum trace-to-trace clearance [mm].
    ///
    /// Also the default inter-phase clearance: when
    /// [`RoutingContext::phase_clearance_mm`] is `None`, `min_space_mm` is used
    /// as `g_phase` in the top-down phase-band equation. That fallback is
    /// intentional and documented (docs/API.md §10.1) — it is never a silent
    /// reuse of an unrelated rule.
    pub min_space_mm: f64,
    /// Whether the pattern declares that its conductors are continuous (end→
    /// start connect within a tolerance) so the validator checks continuity.
    pub expects_continuous: bool,
    /// Pattern-specific numeric parameters (e.g. `num_strands`, `angle_deg`).
    pub params: HashMap<String, f64>,
    /// Magnetic pole pitch [mm] (`magnet_width + magnet_gap`) of the mover the
    /// stator serves. This is the centre-to-centre distance between adjacent
    /// north and south poles (`tau_p` in the phase-band width equations).
    /// Optional so patterns that do not care about the magnet layout stay
    /// decoupled; patterns that DO use it can align their repeating unit (e.g.
    /// the braid's diamond period) to the pole pitch and regenerate geometry
    /// when the magnet pattern changes.
    #[serde(default)]
    pub magnet_pitch_mm: Option<f64>,
    /// Full span of the mover's magnet array [mm] (`magnet_count × pitch`).
    /// Together with `magnet_pitch_mm` lets a pattern derive how many repeating
    /// units cover the mover (e.g. braid periods over the magnet-array span).
    #[serde(default)]
    pub magnet_array_span_mm: Option<f64>,
    /// Explicit inter-phase clearance `g_phase` [mm] used by the top-down
    /// phase-band equation (`max_phase_band_width = tau_p / phases - g_phase`)
    /// and reported as `RoutingDimensions.phase_clearance_mm`.
    ///
    /// This is an explicit INPUT, not a derived quantity. When `None` it falls
    /// back to [`RoutingContext::min_space_mm`] — a documented compatibility
    /// fallback for contexts that do not distinguish the phase-to-phase gap
    /// from the trace-to-trace clearance (docs/API.md §10.1).
    #[serde(default)]
    pub phase_clearance_mm: Option<f64>,
}

impl RoutingContext {
    /// Convenience: read a numeric parameter or fall back to `default`.
    pub fn param(&self, key: &str, default: f64) -> f64 {
        self.params.get(key).copied().unwrap_or(default)
    }

    /// Copper trace width to lay out geometry with: the nominal width when
    /// set, otherwise the minimum (older contexts and unitless callers).
    pub fn trace_width(&self) -> f64 {
        if self.trace_width_mm.is_finite() && self.trace_width_mm > 0.0 {
            self.trace_width_mm
        } else {
            self.min_trace_mm
        }
    }

    /// Resolved pole pitch [mm] when the magnet layout was provided.
    pub fn magnet_pitch(&self) -> Option<f64> {
        self.magnet_pitch_mm.filter(|p| *p > 0.0)
    }

    /// Resolved mover magnet-array span [mm] when the magnet layout was
    /// provided.
    pub fn magnet_array_span(&self) -> Option<f64> {
        self.magnet_array_span_mm
    }
}
