//! Editable B-spline centerlines. Tessellation belongs in format adapters.

use crate::{Point, RouteSegment};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RouteSpline {
    pub degree: usize,
    pub knots: Vec<f64>,
    pub control_points: Vec<Point>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub weights: Vec<f64>,
    pub layer: u32,
    pub net: String,
    pub is_active: bool,
}

impl RouteSpline {
    pub fn validate(&self) -> Result<(), String> {
        let n = self.control_points.len();
        if self.degree == 0
            || self.degree > 10
            || n <= self.degree
            || self.knots.len() != n + self.degree + 1
            || self.knots.iter().any(|v| !v.is_finite())
            || self.knots.windows(2).any(|p| p[0] > p[1])
            || self.knots[self.degree] >= self.knots[n]
            || self
                .control_points
                .iter()
                .any(|p| !p.x.is_finite() || !p.y.is_finite())
            || (!self.weights.is_empty()
                && (self.weights.len() != n
                    || self.weights.iter().any(|v| !v.is_finite() || *v <= 0.0)))
        {
            return Err("Invalid spline degree, knots, control points or weights".into());
        }
        Ok(())
    }

    /// Rational de Boor evaluation on the spline's active knot interval.
    pub fn point_at(&self, t: f64) -> Point {
        let n = self.control_points.len();
        let t = t.clamp(self.knots[self.degree], self.knots[n]);
        let span = if t >= self.knots[n] {
            n - 1
        } else {
            (self.degree..n)
                .find(|&i| t < self.knots[i + 1])
                .unwrap_or(n - 1)
        };
        let mut d: Vec<[f64; 3]> = (span - self.degree..=span)
            .map(|i| {
                let w = self.weights.get(i).copied().unwrap_or(1.0);
                [
                    self.control_points[i].x * w,
                    self.control_points[i].y * w,
                    w,
                ]
            })
            .collect();
        for r in 1..=self.degree {
            for j in (r..=self.degree).rev() {
                let i = span - self.degree + j;
                let denominator = self.knots[i + self.degree + 1 - r] - self.knots[i];
                let a = if denominator == 0.0 {
                    0.0
                } else {
                    (t - self.knots[i]) / denominator
                };
                for axis in 0..3 {
                    d[j][axis] = (1.0 - a) * d[j - 1][axis] + a * d[j][axis];
                }
            }
        }
        let p = d[self.degree];
        Point::new(p[0] / p[2], p[1] / p[2])
    }

    /// For consumers without spline support, sample each nonzero knot span.
    /// The control-polygon length bounds how much detail must be retained.
    pub fn tessellate(&self, step_mm: f64) -> Result<Vec<RouteSegment>, String> {
        self.validate()?;
        if !step_mm.is_finite() || step_mm <= 0.0 {
            return Err("Spline sampling step must be positive and finite".into());
        }
        let length: f64 = self
            .control_points
            .windows(2)
            .map(|p| p[0].distance_to(p[1]))
            .sum();
        let count = (length / step_mm).ceil().max(1.0);
        if !count.is_finite() || count > 100_000.0 {
            return Err("Spline exceeds the sampling limit".into());
        }
        let lo = self.knots[self.degree];
        let hi = self.knots[self.control_points.len()];
        let mut points = vec![self.point_at(lo)];
        for pair in self.knots[self.degree..=self.control_points.len()].windows(2) {
            if pair[0] == pair[1] {
                continue;
            }
            let samples = (count * (pair[1] - pair[0]) / (hi - lo)).ceil().max(1.0) as usize;
            for i in 1..=samples {
                points
                    .push(self.point_at(pair[0] + (pair[1] - pair[0]) * i as f64 / samples as f64));
            }
        }
        Ok(points
            .windows(2)
            .map(|p| RouteSegment {
                start: p[0],
                end: p[1],
                layer: self.layer,
                net: self.net.clone(),
                is_active: self.is_active,
            })
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn quarter_circle() -> RouteSpline {
        RouteSpline {
            degree: 2,
            knots: vec![0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
            control_points: vec![
                Point::new(1.0, 0.0),
                Point::new(1.0, 1.0),
                Point::new(0.0, 1.0),
            ],
            weights: vec![1.0, 0.5_f64.sqrt(), 1.0],
            layer: 1,
            net: "CL1".into(),
            is_active: true,
        }
    }

    #[test]
    fn evaluates_rational_spline_and_samples_only_when_requested() {
        let s = quarter_circle();
        s.validate().unwrap();
        for i in 0..=100 {
            let p = s.point_at(i as f64 / 100.0);
            assert!((p.x.hypot(p.y) - 1.0).abs() < 1e-12);
        }
        let segments = s.tessellate(0.1).unwrap();
        assert_eq!(segments[0].start, Point::new(1.0, 0.0));
        assert_eq!(segments.last().unwrap().end, Point::new(0.0, 1.0));
        assert!(segments.windows(2).all(|p| p[0].end == p[1].start));
        assert!(segments
            .iter()
            .all(|p| p.layer == 1 && p.net == "CL1" && p.is_active));
        assert_eq!(s.control_points.len(), 3);
    }

    #[test]
    fn rejects_malformed_splines_and_unbounded_sampling() {
        let s = quarter_circle();
        for malformed in [
            RouteSpline {
                degree: 0,
                ..s.clone()
            },
            RouteSpline {
                knots: vec![0.0; 6],
                ..s.clone()
            },
            RouteSpline {
                weights: vec![1.0],
                ..s.clone()
            },
            RouteSpline {
                weights: vec![1.0, f64::NAN, 1.0],
                ..s.clone()
            },
        ] {
            assert!(malformed.validate().is_err());
        }
        assert!(s.tessellate(0.0).is_err());
        assert!(s.tessellate(1e-300).is_err());
    }
}
