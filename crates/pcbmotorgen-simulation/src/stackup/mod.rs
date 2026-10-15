//! Height stack and friction budget. Electrical loss and driver limits live
//! in [`crate::drive`].

pub mod friction;
pub mod height_stack;

pub use friction::{mu_bearing, FrictionEstimator};
pub use height_stack::HeightStackCalculator;
