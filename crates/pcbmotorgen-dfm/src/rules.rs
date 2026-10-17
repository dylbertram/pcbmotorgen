//! Design rules (DFM) that govern trace width, clearance, and via sizing.
//!
//! The DFM crate owns trace width and via size. A [`DesignRules`] snapshot is
//! applied when (a) checking interference on a
//! [`RoutingResult`](pcbmotorgen_routing::model::RoutingResult) and (b)
//! describing the geometry to downstream consumers (the KiCad writer), which
//! converts these millimetre sizes into nanometres without re-deriving them.
//!
//! The [`RoutingContext`](pcbmotorgen_routing::context::RoutingContext) fields
//! `min_trace_mm` / `min_space_mm` / `phase_clearance_mm` are part of the
//! routing wire contract (patterns consume them for layout and phase-band
//! math); they are not moved here. The application bridges the same config
//! values into a `DesignRules` snapshot, and this crate reads the snapshot for
//! sizing and DRC clearance decisions downstream.
//!
//! All values in millimetres.

use serde::{Deserialize, Serialize};

/// Minimum manufacturable trace width [mm].
const DEFAULT_MIN_TRACE_MM: f64 = 0.127; // 5 mil
/// Nominal (actual) copper trace width [mm].
const DEFAULT_TRACE_WIDTH_MM: f64 = 0.127; // 5 mil
/// Minimum trace-to-trace clearance [mm].
const DEFAULT_MIN_SPACE_MM: f64 = 0.127; // 5 mil
/// Minimum via drill diameter [mm].
const DEFAULT_MIN_VIA_DRILL_MM: f64 = 0.2;
/// Minimum via annular ring width [mm].
const DEFAULT_MIN_VIA_ANNULAR_RING_MM: f64 = 0.1;

/// A snapshot of the DFM rules applied to generated routing geometry.
///
/// Patterns receive the board + phase dimensions via
/// [`RoutingContext`](pcbmotorgen_routing::context::RoutingContext); trace
/// width, clearance, and via sizing live here so the DFM crate is the
/// authority on those values (per the crate division, kata 0rgs). Downstream
/// consumers (e.g. the KiCad writer) read the sizes from this spec — they
/// never decide them.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(from = "StoredDesignRules")]
pub struct DesignRules {
    /// Minimum manufacturable trace width [mm] — the design-rule floor.
    pub min_trace_mm: f64,
    /// Nominal (actual) copper trace width [mm] written to the board and DXF.
    /// Independent of the `min_trace_mm` floor so a design can use wider
    /// copper than the process minimum.
    pub trace_width_mm: f64,
    /// Minimum trace-to-trace clearance [mm].
    pub min_space_mm: f64,
    /// Minimum via drill diameter [mm].
    pub min_via_drill_mm: f64,
    /// Minimum via annular ring width [mm].
    pub min_via_annular_ring_mm: f64,
}

#[derive(Deserialize)]
struct StoredDesignRules {
    min_trace_mm: f64,
    trace_width_mm: Option<f64>,
    min_space_mm: f64,
    min_via_drill_mm: f64,
    min_via_annular_ring_mm: f64,
}

impl From<StoredDesignRules> for DesignRules {
    fn from(saved: StoredDesignRules) -> Self {
        Self {
            min_trace_mm: saved.min_trace_mm,
            trace_width_mm: saved.trace_width_mm.unwrap_or(saved.min_trace_mm),
            min_space_mm: saved.min_space_mm,
            min_via_drill_mm: saved.min_via_drill_mm,
            min_via_annular_ring_mm: saved.min_via_annular_ring_mm,
        }
    }
}

impl Default for DesignRules {
    fn default() -> Self {
        Self {
            min_trace_mm: DEFAULT_MIN_TRACE_MM,
            trace_width_mm: DEFAULT_TRACE_WIDTH_MM,
            min_space_mm: DEFAULT_MIN_SPACE_MM,
            min_via_drill_mm: DEFAULT_MIN_VIA_DRILL_MM,
            min_via_annular_ring_mm: DEFAULT_MIN_VIA_ANNULAR_RING_MM,
        }
    }
}

impl DesignRules {
    /// Reject invalid copper sizing rather than silently widening a track.
    pub fn validate_trace_width(&self) -> Result<(), String> {
        if !self.min_trace_mm.is_finite() || self.min_trace_mm <= 0.0
            || !self.trace_width_mm.is_finite() || self.trace_width_mm < self.min_trace_mm {
            return Err(format!("Trace width must be finite and at least the positive minimum trace width (nominal {} mm, minimum {} mm)", self.trace_width_mm, self.min_trace_mm));
        }
        Ok(())
    }

    /// Minimum via pad diameter [mm] = drill + 2 × annular ring.
    pub fn via_pad_diameter_mm(&self) -> f64 {
        self.min_via_drill_mm + 2.0 * self.min_via_annular_ring_mm
    }

    /// Minimum via pad radius [mm].
    pub fn via_pad_radius_mm(&self) -> f64 {
        self.via_pad_diameter_mm() / 2.0
    }

    /// Default plated IO pad diameter [mm] — identical to the via pad
    /// diameter (`drill + 2 × annular ring`).
    ///
    /// This is the sizing authority for THT
    /// [`IoPad`](pcbmotorgen_routing::io::IoPad) stacks: patterns read the
    /// diameter from here (or size pads explicitly) and the writers carry the
    /// declared size through — nothing downstream decides pad dimensions.
    pub fn io_tht_pad_diameter_mm(&self) -> f64 {
        self.via_pad_diameter_mm()
    }

    /// Bridge: the canonical host IO fanout options from this rule snapshot
    /// (kata xa0f) — a THT connector row sized by this authority
    /// (`io_tht_pad_diameter_mm` pad copper, `min_via_drill_mm` drill). The
    /// routing crate's IO generator reads sizes from its options and never
    /// decides them, so this bridge is the sizing handoff.
    pub fn io_fanout_options(&self) -> pcbmotorgen_routing::IoFanoutOptions {
        pcbmotorgen_routing::IoFanoutOptions::tht(
            self.io_tht_pad_diameter_mm(),
            self.min_via_drill_mm,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_millimetres() {
        let rules = DesignRules::default();
        assert_eq!(rules.min_trace_mm, 0.127);
        assert_eq!(rules.trace_width_mm, 0.127);
        assert_eq!(rules.min_space_mm, 0.127);
        assert_eq!(rules.min_via_drill_mm, 0.2);
        assert_eq!(rules.min_via_annular_ring_mm, 0.1);
        assert_eq!(rules.via_pad_diameter_mm(), 0.4);
        assert_eq!(rules.io_tht_pad_diameter_mm(), 0.4);
    }

    #[test]
    fn nominal_width_must_clear_the_floor_without_clamping() {
        for width in [0.05, 0.0, -1.0, f64::NAN, f64::INFINITY] {
            assert!(DesignRules { trace_width_mm: width, ..Default::default() }.validate_trace_width().is_err());
        }
        DesignRules { trace_width_mm: 0.3, ..Default::default() }.validate_trace_width().unwrap();
    }

    #[test]
    fn derived_pad_sizing_follows_drill_and_ring() {
        let rules = DesignRules {
            min_via_drill_mm: 0.3,
            min_via_annular_ring_mm: 0.05,
            ..DesignRules::default()
        };
        assert_eq!(rules.via_pad_diameter_mm(), 0.4);
        assert_eq!(rules.via_pad_radius_mm(), 0.2);
        assert_eq!(rules.io_tht_pad_diameter_mm(), rules.via_pad_diameter_mm());
    }

    #[test]
    fn serde_shape_is_stable() {
        // The struct moved crates (kata 0rgs) but its serde shape must stay
        // byte-compatible for any serialized snapshots.
        let rules = DesignRules::default();
        let json = serde_json::to_string(&rules).unwrap();
        assert_eq!(
            json,
            r#"{"min_trace_mm":0.127,"trace_width_mm":0.127,"min_space_mm":0.127,"min_via_drill_mm":0.2,"min_via_annular_ring_mm":0.1}"#
        );
        let back: DesignRules = serde_json::from_str(&json).unwrap();
        assert_eq!(back, rules);
        // A payload from before the nominal width existed defaults to the floor.
        let legacy: DesignRules = serde_json::from_str(
            r#"{"min_trace_mm":0.2,"min_space_mm":0.15,"min_via_drill_mm":0.3,"min_via_annular_ring_mm":0.1}"#,
        )
        .unwrap();
        assert_eq!(legacy.trace_width_mm, 0.2);
        assert_eq!(legacy.min_trace_mm, 0.2);
    }

    #[test]
    fn io_fanout_options_bridge_sizes_from_the_rules() {
        let rules = DesignRules::default();
        let opts = rules.io_fanout_options();
        assert_eq!(opts.pad_diameter_mm, rules.io_tht_pad_diameter_mm());
        assert_eq!(opts.drill_mm, Some(rules.min_via_drill_mm));
        assert!(opts.drill_mm.unwrap() > 0.0, "drill is positive");
    }
}
