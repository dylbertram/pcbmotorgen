//! Magnet builders for [`MagnetArray`](super::MagnetArray).
//!
//! Each submodule owns one builder family and a `pub(crate)` builder
//! method on `MagnetArray`, which the parent module's `build_assembly`
//! calls. (Inherent methods resolve crate-wide, so no re-exports
//! are needed.)

pub(crate) mod alternating;
pub(crate) mod backplane;