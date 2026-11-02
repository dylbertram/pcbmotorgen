//! Bundled routing patterns.
//!
//! [`infinity`] is the reference "infinity" diamond braid ported from
//! `.ref/pcbBraid` (after Verbeek & Dehez).

pub mod infinity;

/// Build the default registry of bundled patterns.
pub fn bundled() -> crate::registry::RoutingRegistry {
    let mut reg = crate::registry::RoutingRegistry::new();
    reg.register(infinity::InfinityBraidPattern);
    reg
}
