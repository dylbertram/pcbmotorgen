//! NdFeB magnet grade → remanence lookup.
//!
//! Data source: PRODUCT_GOALS.md §3.C.

use serde::{Deserialize, Serialize};

pub const CUSTOM_GRADE: &str = "Custom";

/// A single NdFeB magnet grade specification.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MagnetGrade {
    pub name: String,
    pub br_min_t: f64,
    pub br_typ_t: f64,
    pub br_max_t: f64,
}

/// Standard grade table: (name, br_min, br_typ, br_max).
pub const MAGNET_GRADES: &[(&str, f64, f64, f64)] = &[
    ("N35", 1.17, 1.19, 1.21),
    ("N38", 1.21, 1.23, 1.25),
    ("N42", 1.28, 1.30, 1.32),
    ("N44", 1.32, 1.34, 1.36),
    ("N48", 1.38, 1.40, 1.42),
    ("N52", 1.43, 1.45, 1.48),
];

/// List of grade names (in order).
pub fn grade_names() -> Vec<&'static str> {
    MAGNET_GRADES.iter().map(|(n, _, _, _)| *n).collect()
}

/// Typical remanence [T] for a grade name (handles suffixes, e.g. "N44H" → "N44").
pub fn get_remanence(grade: &str) -> Option<f64> {
    let base = extract_base_grade(grade)?;
    MAGNET_GRADES
        .iter()
        .find(|(n, _, _, _)| *n == base)
        .map(|(_, _, typ, _)| *typ)
}

/// Full grade spec for a grade name (handles suffixes).
pub fn get_grade(grade: &str) -> Option<MagnetGrade> {
    let base = extract_base_grade(grade)?;
    MAGNET_GRADES
        .iter()
        .find(|(n, _, _, _)| *n == base)
        .map(|(n, min, typ, max)| MagnetGrade {
            name: n.to_string(),
            br_min_t: *min,
            br_typ_t: *typ,
            br_max_t: *max,
        })
}

/// Extract base grade (e.g. "N44" from "N44H" or "n44sh").
fn extract_base_grade(grade: &str) -> Option<String> {
    let g = grade.trim();
    let lower = g.to_ascii_lowercase();
    if let Some(suffix) = lower.strip_prefix('n') {
        let digits: String = suffix
            .chars()
            .take_while(|c| c.is_ascii_digit())
            .collect();
        if !digits.is_empty() {
            return Some(format!("N{}", digits));
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_remanence_n44() {
        assert!((get_remanence("N44").unwrap() - 1.34).abs() < 1e-6);
    }

    #[test]
    fn test_get_remanence_n44h_suffix() {
        assert!((get_remanence("N44H").unwrap() - 1.34).abs() < 1e-6);
    }

    #[test]
    fn test_get_remanence_n52() {
        assert!((get_remanence("N52").unwrap() - 1.45).abs() < 1e-6);
    }

    #[test]
    fn test_get_remanence_unknown_returns_none() {
        assert!(get_remanence("X99").is_none());
    }

    #[test]
    fn test_get_remanence_custom_returns_none() {
        assert!(get_remanence("Custom").is_none());
    }

    #[test]
    fn test_get_grade_n42() {
        let g = get_grade("N42").unwrap();
        assert_eq!(g.name, "N42");
        assert!((g.br_typ_t - 1.30).abs() < 1e-6);
    }

    #[test]
    fn test_grade_names_includes_n44() {
        assert!(grade_names().contains(&"N44"));
    }
}
