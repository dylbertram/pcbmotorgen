//! Native Rust `cdylib` routing-pattern plugin loader.
//!
//! # Plugin ABI contract
//!
//! A plugin is a `cdylib` (`.dylib` / `.so` / `.dll`) compiled against the same
//! `pcbmotorgen-routing` crate, exposing three `#[no_mangle] extern "C"`
//! symbols:
//!
//! ```ignore
//! static pcbmotorgen_ROUTING_PLUGIN_API: u32      // = 3 (end-type metadata)
//! unsafe extern "C" fn pcbmotorgen_routing_plugin_create() -> *mut c_void
//! unsafe extern "C" fn pcbmotorgen_routing_plugin_destroy(v: *mut c_void)
//! ```
//!
//! `create` returns a heap `Box<Box<dyn RoutingPattern>>` (double boxed so the
//! trait-object fat pointer, which carries the vtable, survives the thin
//! `*mut c_void` crossing). `destroy` reconstructs and drops it. See the
//! `routing-plugin-example` in the crate's `examples/` for a reference plugin.
//!
//! Both host and plugin must link the same version of `pcbmotorgen-routing`
//! so the vtable layout matches. Loaded at runtime, so a plugin can be swapped
//! without recompiling the app.

use std::ffi::c_void;
use std::sync::Arc;

use libloading::{Library, Symbol};

use crate::context::RoutingContext;
use crate::error::RoutingError;
use crate::model::RoutingResult;
use crate::pattern::RoutingPattern;

/// API version a plugin must declare. Bump on breaking ABI changes.
pub const PLUGIN_API_VERSION: u32 = 3;

/// A loaded native plugin, keeping its backing library alive for the lifetime
/// of the pattern.
pub struct NativePlugin {
    _lib: Arc<Library>,
    pattern: Box<dyn RoutingPattern>,
}

impl NativePlugin {
    /// Load a pattern from a `cdylib` at `path`.
    ///
    /// # Safety
    /// Loading an arbitrary dynamic library executes its constructor code. Only
    /// load libraries you trust.
    pub unsafe fn load(path: &std::path::Path) -> Result<Self, String> {
        let lib = Library::new(path)
            .map_err(|e| format!("failed to open plugin library {}: {e}", path.display()))?;
        let lib = Arc::new(lib);

        let api_version: Symbol<u32> = lib
            .get(b"pcbmotorgen_ROUTING_PLUGIN_API\0")
            .map_err(|e| format!("plugin missing pcbmotorgen_ROUTING_PLUGIN_API symbol: {e}"))?;
        if *api_version != PLUGIN_API_VERSION {
            return Err(format!(
                "plugin API version mismatch: got {}, host expects {}",
                *api_version, PLUGIN_API_VERSION
            ));
        }

        type Create = unsafe extern "C" fn() -> *mut c_void;
        type Destroy = unsafe extern "C" fn(*mut c_void);

        let create: Symbol<Create> = lib
            .get(b"pcbmotorgen_routing_plugin_create\0")
            .map_err(|e| format!("plugin missing create symbol: {e}"))?;
        let _destroy: Symbol<Destroy> = lib
            .get(b"pcbmotorgen_routing_plugin_destroy\0")
            .map_err(|e| format!("plugin missing destroy symbol: {e}"))?;

        let raw = create();
        if raw.is_null() {
            return Err("plugin create returned a null pointer".to_string());
        }

        let pattern: Box<dyn RoutingPattern> = unsafe {
            let outer = Box::from_raw(raw as *mut Box<dyn RoutingPattern>);
            // Move the inner `Box<dyn RoutingPattern>` out; moving a T out of
            // a Box<T> via deref is legal, and the outer Box is then dropped
            // at scope end (freeing its allocation).
            *outer
        };

        Ok(NativePlugin {
            _lib: lib,
            pattern,
        })
    }

    /// Borrow the loaded pattern.
    pub fn pattern(&self) -> &dyn RoutingPattern {
        self.pattern.as_ref()
    }
}

impl RoutingPattern for NativePlugin {
    fn metadata(&self) -> crate::PluginMetadata {
        self.pattern.metadata()
    }

    fn id(&self) -> &str {
        self.pattern.id()
    }

    fn display_name(&self) -> &str {
        self.pattern.display_name()
    }

    fn author(&self) -> &str {
        self.pattern.author()
    }

    fn version(&self) -> &str {
        self.pattern.version()
    }

    fn description(&self) -> &str {
        self.pattern.description()
    }

    fn parameters(&self) -> Vec<crate::pattern::PatternParameter> {
        self.pattern.parameters()
    }

    fn min_layers(&self) -> Option<u32> {
        self.pattern.min_layers()
    }

    fn max_layers(&self) -> Option<u32> {
        self.pattern.max_layers()
    }

    fn layers_multiple_of(&self) -> Option<u32> {
        self.pattern.layers_multiple_of()
    }

    fn expects_continuous(&self) -> bool {
        self.pattern.expects_continuous()
    }

    fn generate(&self, ctx: &RoutingContext) -> Result<RoutingResult, RoutingError> {
        self.pattern.generate(ctx)
    }
}

impl Drop for NativePlugin {
    fn drop(&mut self) {
        // Nothing further needed: the Box<dyn RoutingPattern> is dropped via
        // `self.pattern`, and `_lib` drops when the Arc refcount hits zero.
    }
}

impl std::fmt::Debug for NativePlugin {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("NativePlugin")
            .field("id", &self.pattern.id())
            .finish()
    }
}
