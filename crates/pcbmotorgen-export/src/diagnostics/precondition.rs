//! Pre-write precondition validation.
//!
//! `validate_write_preconditions` is a pure function comparing the
//! generation spec against the live [`BoardDiagnostics`] snapshot. It
//! returns [`PreconditionWarning`] entries (Info / Warning / Error) so the
//! UI can show "your config is 4-layer but your board is 2-layer — reduce
//! to 2" before any track is written.

use pcbmotorgen_dfm::DesignRules;

use super::BoardDiagnostics;

// ---------------------------------------------------------------------------
// PreconditionWarning
// ---------------------------------------------------------------------------

/// Severity of a [`PreconditionWarning`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PreconditionLevel {
    /// Informational — design still works, but a tweak is recommended.
    Info,
    /// Warning — design will likely underperform, but won't outright fail.
    Warning,
    /// Error — the write will probably fail or produce broken geometry.
    Error,
}

/// One warning or recommendation about the (config, board) pair.
///
/// Produced by [`validate_write_preconditions`]. The UI is expected to render
/// each `message` verbatim and colour-code by `level`. The `field` is an
/// optional machine-readable key (`"num_layers"`, `"active_area_length_m"`,
/// …) that the UI can use to highlight the offending input control.
#[derive(Debug, Clone, PartialEq)]
pub struct PreconditionWarning {
    pub level: PreconditionLevel,
    pub field: Option<String>,
    pub message: String,
}

impl PreconditionWarning {
    /// Construct a new warning of the given level.
    pub fn new(level: PreconditionLevel, field: Option<&str>, message: impl Into<String>) -> Self {
        Self {
            level,
            field: field.map(String::from),
            message: message.into(),
        }
    }

    /// Construct an Info-level warning.
    pub fn info(field: Option<&str>, message: impl Into<String>) -> Self {
        Self::new(PreconditionLevel::Info, field, message)
    }
    /// Construct a Warning-level warning.
    pub fn warn(field: Option<&str>, message: impl Into<String>) -> Self {
        Self::new(PreconditionLevel::Warning, field, message)
    }
    /// Construct an Error-level warning.
    pub fn error(field: Option<&str>, message: impl Into<String>) -> Self {
        Self::new(PreconditionLevel::Error, field, message)
    }
}

// ---------------------------------------------------------------------------
// validate_write_preconditions
// ---------------------------------------------------------------------------

/// Pure function — does not touch KiCad. Returns the list of warnings/errors
/// that the UI should display before letting the user click "Write to Board".
///
/// All layer-count checks operate on `num_layers` (the user-selected layer
/// count). It is perfectly valid for a user to select 4 layers on a
/// 12-layer-capable board; the check must fire on the user intent, not the
/// ceiling.
///
/// Implemented checks (extend as new ones are needed):
/// 1. **Layer count** — `num_layers > diagnostics.copper_layer_count`
///    is an `Error` (we'd write tracks to non-existent layers).
/// 2. **Layer count zero** — `num_layers == 0` is an `Error`
///    (zero iterations → no coils).
/// 3. **Active area vs board width** — if the board dimensions are queryable
///    and `active_area_length_m > board_width`, emits a `Warning`.
/// 4. **Board width vs board edge-cut** — same idea for the y dimension.
/// 5. **Invalid design rules** — `rules.min_trace_mm` / `rules.min_space_mm`
///    must be positive, otherwise no valid geometry can be produced.
pub fn validate_write_preconditions(
    rules: &DesignRules,
    num_layers: u32,
    active_area_length_m: f64,
    board_width_m: f64,
    diagnostics: &BoardDiagnostics,
) -> Vec<PreconditionWarning> {
    let mut out: Vec<PreconditionWarning> = Vec::new();

    // (1) num_layers > board's copper layer count → Error
    if num_layers > diagnostics.copper_layer_count && diagnostics.copper_layer_count > 0 {
        out.push(PreconditionWarning::error(
            Some("num_layers"),
            format!(
                "Your config requests {} layer(s) but the board '{}' only has {}. \
                 Reduce num_layers to {} to match the board.",
                num_layers,
                diagnostics.board_name,
                diagnostics.copper_layer_count,
                diagnostics.copper_layer_count,
            ),
        ));
    }

    // (2) num_layers == 0 → Error (no iterations → no coils)
    if num_layers == 0 {
        out.push(PreconditionWarning::error(
            Some("num_layers"),
            "num_layers is 0 — no coils can be generated. Set at least 2.",
        ));
    }

    // (3) active_area_length_m > board width (when board dims are known)
    let board_w = diagnostics.board_width_mm();
    if board_w > 0.0 {
        let active_mm = active_area_length_m * 1e3;
        if active_mm > board_w {
            out.push(PreconditionWarning::warn(
                Some("active_area_length_m"),
                format!(
                    "Your active area is {:.1} mm but the board edge-cut is only {:.1} mm wide. \
                     Either reduce active_area_length, use a larger board, or expand the \
                     board's edge cuts.",
                    active_mm, board_w,
                ),
            ));
        }
    }

    // (4) board_width_m > board height (when board dims are known)
    let board_h = diagnostics.board_height_mm();
    if board_h > 0.0 {
        let cfg_board_w_mm = board_width_m * 1e3;
        if cfg_board_w_mm > board_h {
            out.push(PreconditionWarning::warn(
                Some("board_width_m"),
                format!(
                    "Your board_width is {:.1} mm but the board edge-cut is only {:.1} mm tall. \
                     Either reduce board_width, or expand the board's edge cuts.",
                    cfg_board_w_mm, board_h,
                ),
            ));
        }
    }

    // (5) Invalid design rules → no valid geometry is possible.
    if !rules.min_trace_mm.is_finite() || !rules.min_space_mm.is_finite()
        || rules.min_trace_mm <= 0.0 || rules.min_space_mm <= 0.0 {
        out.push(PreconditionWarning::error(
            Some("design_rules"),
            format!(
                "Design rules are not positive (min_trace_mm={}, min_space_mm={}). \
                 Cannot produce manufacturable geometry.",
                rules.min_trace_mm, rules.min_space_mm
            ),
        ));
    }

    // (6) The nominal trace width must clear the manufacturing floor.
    if !rules.trace_width_mm.is_finite() || rules.trace_width_mm <= 0.0 || rules.trace_width_mm < rules.min_trace_mm {
        out.push(PreconditionWarning::error(
            Some("trace_width_mm"),
            format!(
                "Nominal trace width ({:.4} mm) is below the minimum trace width \
                  ({:.4} mm). Increase the trace width or lower \
                 the minimum rule.",
                rules.trace_width_mm, rules.min_trace_mm
            ),
        ));
    }

    out
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
use super::*;

/// Millimetres → metres.
fn mm(v: f64) -> f64 {
    v * 1e-3
}

/// `DesignRules` matching the old `default_config` helper (5 mil trace/space,
/// 0.2 mm via drill, 0.1 mm annular ring).
fn braid_rules() -> DesignRules {
    DesignRules {
        min_trace_mm: 0.127,
        trace_width_mm: 0.127,
        min_space_mm: 0.127,
        min_via_drill_mm: 0.2,
        min_via_annular_ring_mm: 0.1,
    }
}

#[test]
fn invalid_nominal_width_blocks_writing_without_silent_resizing() {
    for width in [0.05, 0.0, f64::NAN, f64::INFINITY] {
        let rules = DesignRules { trace_width_mm: width, ..braid_rules() };
        let warnings = validate_write_preconditions(&rules, 4, ACTIVE_AREA_M, BOARD_WIDTH_M, &empty_diagnostics());
        assert!(warnings.iter().any(|w| w.field.as_deref() == Some("trace_width_mm") && w.level == PreconditionLevel::Error));
        assert!(!warnings.iter().any(|w| w.message.contains("using the minimum")));
    }
}

/// Active area used by the braid precondition tests.
const ACTIVE_AREA_M: f64 = 0.6;

/// Board width used by the braid precondition tests.
const BOARD_WIDTH_M: f64 = 0.02;

fn empty_diagnostics() -> BoardDiagnostics {
    BoardDiagnostics {
        board_name: "test.kicad_pcb".into(),
        copper_layer_count: 0,
        board_x_min_mm: 0.0,
        board_x_max_mm: 0.0,
        board_y_min_mm: 0.0,
        board_y_max_mm: 0.0,
        available_net_classes: Vec::new(),
    }
}

// --- validate_write_preconditions: layer count ---

#[test]
fn test_validate_layer_mismatch_is_error() {
    // User picked 6 layers, board only has 4 → Error.
    let rules = braid_rules();
    let mut d = empty_diagnostics();
    d.copper_layer_count = 4; // board only has 4
    let warnings = validate_write_preconditions(&rules, 6, ACTIVE_AREA_M, BOARD_WIDTH_M, &d);
    let errs: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| w.level == PreconditionLevel::Error)
        .collect();
    assert!(!errs.is_empty(), "expected an error for layer mismatch");
    assert!(errs[0].message.contains("6"));
    assert!(errs[0].message.contains("4"));
    assert_eq!(errs[0].field.as_deref(), Some("num_layers"));
}

/// Matching layer counts must be silent; a user above the board's actual
/// layer count must report the user's number.
#[test]
fn test_validate_layer_mismatch_reports_user_num_layers() {
    let rules = braid_rules();
    let mut d = empty_diagnostics();
    d.copper_layer_count = 4; // board has 4 layers
    // num_layers = 4 → matches the board, no layer-count error.
    let warnings = validate_write_preconditions(&rules, 4, ACTIVE_AREA_M, BOARD_WIDTH_M, &d);
    let layer_errs: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| {
            w.level == PreconditionLevel::Error && w.field.as_deref() == Some("num_layers")
        })
        .collect();
    assert!(
        layer_errs.is_empty(),
        "no layer-count error expected for matching 4-layer config + 4-layer board, got: {:?}",
        layer_errs
    );

    // Push the user above the board: num_layers=6, board=4 → the error must
    // report the 6 the user asked for.
    let warnings = validate_write_preconditions(&rules, 6, ACTIVE_AREA_M, BOARD_WIDTH_M, &d);
    let layer_errs: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| {
            w.level == PreconditionLevel::Error && w.field.as_deref() == Some("num_layers")
        })
        .collect();
    assert_eq!(layer_errs.len(), 1, "expected exactly one layer-count error");
    let msg = &layer_errs[0].message;
    assert!(
        msg.contains("6 layer(s)"),
        "error must report the user-selected num_layers (6), got: {}",
        msg
    );
}

#[test]
fn test_validate_layer_match_no_warning() {
    let rules = braid_rules();
    let mut d = empty_diagnostics();
    d.copper_layer_count = 4;
    let warnings = validate_write_preconditions(&rules, 4, ACTIVE_AREA_M, BOARD_WIDTH_M, &d);
    let errs: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| {
            w.level == PreconditionLevel::Error && w.field.as_deref() == Some("num_layers")
        })
        .collect();
    assert!(errs.is_empty(), "got unexpected error: {:?}", errs);
}

#[test]
fn test_validate_zero_layers_is_error() {
    let rules = braid_rules();
    let warnings = validate_write_preconditions(&rules, 0, ACTIVE_AREA_M, BOARD_WIDTH_M, &empty_diagnostics());
    let errs: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| w.level == PreconditionLevel::Error)
        .collect();
    assert!(!errs.is_empty());
    assert!(errs[0].message.to_lowercase().contains("num_layers"));
}

// --- validate_write_preconditions: dimensions ---

#[test]
fn test_validate_active_area_too_wide_warns() {
    let rules = braid_rules();
    let mut d = empty_diagnostics();
    d.board_x_min_mm = 0.0;
    d.board_x_max_mm = 100.0; // 100 mm board
    let warnings = validate_write_preconditions(&rules, 4, mm(500.0), BOARD_WIDTH_M, &d);
    let warns: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| w.field.as_deref() == Some("active_area_length_m"))
        .collect();
    assert!(!warns.is_empty(), "expected active_area warning");
    assert!(warns[0].message.contains("500"));
    assert!(warns[0].message.contains("100"));
}

#[test]
fn test_validate_active_area_fits_no_warning() {
    let rules = braid_rules();
    let mut d = empty_diagnostics();
    d.board_x_min_mm = 0.0;
    d.board_x_max_mm = 250.0;
    let warnings = validate_write_preconditions(&rules, 4, mm(195.0), BOARD_WIDTH_M, &d);
    let warns: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| w.field.as_deref() == Some("active_area_length_m"))
        .collect();
    assert!(warns.is_empty());
}

#[test]
fn test_validate_board_dimensions_unknown_no_warning() {
    // Diagnostics with zero board dims → no dimension warning, even if
    // active_area is huge (we just don't know how big the board is).
    let rules = braid_rules();
    let d = empty_diagnostics(); // all zeros
    let warnings = validate_write_preconditions(&rules, 4, mm(500.0), mm(50.0), &d);
    let dim_warns: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| {
            w.field.as_deref() == Some("active_area_length_m")
                || w.field.as_deref() == Some("board_width_m")
        })
        .collect();
    assert!(dim_warns.is_empty());
}

// --- validate_write_preconditions: design rules ---

#[test]
fn test_validate_zero_or_negative_design_rules_errors() {
    let mut rules = braid_rules();
    rules.min_space_mm = 0.0;
    let warnings = validate_write_preconditions(&rules, 4, ACTIVE_AREA_M, BOARD_WIDTH_M, &empty_diagnostics());
    let errs: Vec<&PreconditionWarning> = warnings
        .iter()
        .filter(|w| w.level == PreconditionLevel::Error)
        .collect();
    assert!(!errs.is_empty(), "invalid design rules must produce an error");
    assert_eq!(errs[0].field.as_deref(), Some("design_rules"));
}
}
