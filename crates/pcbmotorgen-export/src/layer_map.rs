//! Layer mapping and unit conversion helpers for the KiCad writer.
//!
//! All pcbmotorgen routing geometry uses **millimetres** for coordinates, while
//! the KiCad IPC API stores everything in **nanometres** (1 mm = 1e6 nm). The
//! helpers here bridge that gap and map zero-based layer indices (as used by
//! the coil generators) to KiCad's [`BoardLayer`] enum values.
//!
//! ## KiCad copper-layer numbering
//! ```text
//! F_Cu  = 3   (top)
//! In1_Cu = 4
//! ...
//! In30_Cu = 33
//! B_Cu  = 34  (bottom)
//! ```
//!
//! The coil generators number layers zero-based from the bottom up:
//! - layer 0            → `B_Cu` (34)
//! - layer total-1      → `F_Cu` (3)
//! - layer n (0<n<total) → `In{n}_Cu` (3 + n)

use crate::BoardLayer;

/// Map a zero-based layer index to the KiCad [`BoardLayer`] enum value.
///
/// See the [module docs](self) for the numbering convention.
pub fn layer_idx_to_board_layer(idx: u32, total_layers: u32) -> BoardLayer {
    if total_layers == 0 {
        return BoardLayer::BlUnknown;
    }
    if idx == 0 {
        BoardLayer::BlBCu
    } else if idx == total_layers - 1 {
        BoardLayer::BlFCu
    } else {
        // Inner copper layers: In{n}_Cu = 3 + n for n in 1..=30 (values 4..=33).
        // prost-generated enums implement TryFrom<i32>.
        let value = 3 + idx as i32;
        BoardLayer::try_from(value).unwrap_or(BoardLayer::BlUnknown)
    }
}

/// Convert millimetres to nanometres (KiCad's internal unit).
///
/// Returns the nearest integer nanometre value (rounded).
pub fn mm_to_nm(mm: f64) -> i64 {
    (mm * 1e6).round() as i64
}

/// Compute the via pad diameter in nanometres.
///
/// `pad_diameter = drill + 2 × annular_ring`
pub fn via_pad_diameter_nm(drill_mm: f64, annular_ring_mm: f64) -> i64 {
    mm_to_nm(drill_mm + 2.0 * annular_ring_mm)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_layer_top_is_fcu() {
        assert_eq!(layer_idx_to_board_layer(3, 4), BoardLayer::BlFCu);
        assert_eq!(layer_idx_to_board_layer(11, 12), BoardLayer::BlFCu);
    }

    #[test]
    fn test_inner_layers() {
        assert_eq!(layer_idx_to_board_layer(1, 4), BoardLayer::BlIn1Cu);
        assert_eq!(layer_idx_to_board_layer(2, 4), BoardLayer::BlIn2Cu);
        assert_eq!(layer_idx_to_board_layer(1, 12), BoardLayer::BlIn1Cu);
        assert_eq!(layer_idx_to_board_layer(10, 12), BoardLayer::BlIn10Cu);
    }

    #[test]
    fn test_zero_layers() {
        assert_eq!(layer_idx_to_board_layer(0, 0), BoardLayer::BlUnknown);
    }

    #[test]
    fn test_mm_to_nm() {
        assert_eq!(mm_to_nm(1.0), 1_000_000);
        assert_eq!(mm_to_nm(20.0), 20_000_000);
        assert_eq!(mm_to_nm(0.0), 0);
    }
}
