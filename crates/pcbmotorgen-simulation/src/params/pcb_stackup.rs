//! Explicit copper/dielectric PCB stack. Surface z=0 faces the mover;
//! copper centers sit inside the board. Solder mask is not part of this stack.
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PcbStackup {
    pub copper_m: Vec<f64>,
    pub dielectric_m: Vec<f64>,
}

impl PcbStackup {
    pub fn thickness_m(&self) -> f64 {
        self.copper_m.iter().chain(&self.dielectric_m).sum()
    }

    pub fn validate(&self, layers: u32, total_m: f64) -> Result<(), String> {
        if layers < 2 || layers > super::MAX_PCB_LAYERS
            || self.copper_m.len() != layers as usize || self.dielectric_m.len() + 1 != layers as usize {
            return Err("PCB stackup must have one copper thickness per layer and one dielectric thickness between adjacent layers".into());
        }
        if self.copper_m.iter().chain(&self.dielectric_m).any(|t| !t.is_finite() || *t <= 0.) {
            return Err("Every PCB copper and dielectric thickness must be positive and finite".into());
        }
        let actual = self.thickness_m();
        if !total_m.is_finite() || !actual.is_finite() || (actual - total_m).abs() > 1e-10 * actual.max(1.) {
            return Err("PCB thickness must equal the sum of the custom copper and dielectric layers".into());
        }
        Ok(())
    }

    pub fn layer_z_m(&self, layer: u32) -> f64 {
        let i = layer as usize;
        let Some(&copper) = self.copper_m.get(i) else { return f64::NAN };
        -self.copper_m[..i].iter().sum::<f64>() - self.dielectric_m[..i.min(self.dielectric_m.len())].iter().sum::<f64>() - copper / 2.
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn physical_centers_and_total_include_every_copper_and_dielectric_layer() {
        let s = PcbStackup { copper_m: vec![35e-6, 18e-6, 70e-6, 35e-6], dielectric_m: vec![0.1e-3, 0.4e-3, 0.142e-3] };
        assert!((s.thickness_m() - 0.8e-3).abs() < 1e-15);
        s.validate(4, 0.8e-3).unwrap();
        for (layer, expected) in [-0.0175e-3, -0.144e-3, -0.588e-3, -0.7825e-3].iter().enumerate() {
            assert!((s.layer_z_m(layer as u32) - expected).abs() < 1e-15);
        }
        assert!(s.validate(6, 0.8e-3).is_err());
        assert!(s.validate(4, 1.6e-3).is_err());
        for bad in [0., -1., f64::NAN, f64::INFINITY] {
            let mut invalid = s.clone(); invalid.dielectric_m[0] = bad;
            assert!(invalid.validate(4, invalid.thickness_m()).is_err());
        }
    }
}
