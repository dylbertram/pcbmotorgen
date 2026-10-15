//! The [`RoutingPattern`] trait — the documented interface every pattern
//! (bundled, Rust crate plugin, or Python runner) implements.

use crate::{error::RoutingError, model::RoutingResult, context::RoutingContext};

pub use ParamType::*;

/// The data type of a pattern parameter.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ParamType {
    /// An integer-valued parameter (e.g. number of strands).
    Int,
    /// A floating-point parameter (e.g. an angle in degrees).
    Float,
}

/// A single user-settable parameter a pattern exposes.
///
/// Patterns declare their configurable knobs here so the UI can render a
/// control and the core can seed defaults. Parameters are carried to the
/// pattern at generate-time via [`RoutingContext::params`]. Quantities that are
/// *derived* from the board (e.g. the infinity braid's amplitude `A` and total
/// length `D_tot`, computed from the active-area width / length) are NOT
/// declared here — only user-editable knobs are.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct PatternParameter {
    /// The key used in `RoutingContext.params` (e.g. `"num_strands"`).
    pub key: String,
    /// Human-readable label for the UI.
    pub label: String,
    /// Optional longer description / tooltip.
    pub description: String,
    /// The expected type (renders an int vs float input).
    pub param_type: ParamType,
    /// Default value.
    pub default: f64,
    /// Optional inclusive minimum.
    pub min: Option<f64>,
    /// Optional inclusive maximum.
    pub max: Option<f64>,
    /// Optional step for the spinner.
    pub step: Option<f64>,
    /// Optional "value must be a multiple of this" constraint (e.g. `2.0` =
    /// even-only strand counts). Validated by the routing crate before
    /// generation (`validate_routing_params`); the app mirrors it onto the
    /// input's step + invalid state. `None` = unconstrained.
    #[serde(default)]
    pub multiple_of: Option<f64>,
    /// Optional closed set of allowed values, each with a display label. When
    /// non-empty the UI renders a choice instead of a number input and the
    /// routing crate rejects any value outside the set
    /// (`validate_routing_params`). Empty = any value in range.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub options: Vec<ParamOption>,
}

/// One allowed value of a choice [`PatternParameter`].
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ParamOption {
    pub value: f64,
    pub label: String,
}

impl ParamOption {
    pub fn new(value: f64, label: impl Into<String>) -> Self {
        Self {
            value,
            label: label.into(),
        }
    }
}

impl PatternParameter {
    pub fn int(
        key: impl Into<String>,
        label: impl Into<String>,
        default: f64,
        min: f64,
        max: f64,
    ) -> Self {
        Self {
            key: key.into(),
            label: label.into(),
            description: String::new(),
            param_type: ParamType::Int,
            default,
            min: Some(min),
            max: Some(max),
            step: Some(1.0),
            multiple_of: None,
            options: Vec::new(),
        }
    }

    pub fn float(
        key: impl Into<String>,
        label: impl Into<String>,
        default: f64,
    ) -> Self {
        Self {
            key: key.into(),
            label: label.into(),
            description: String::new(),
            param_type: ParamType::Float,
            default,
            min: None,
            max: None,
            step: None,
            multiple_of: None,
            options: Vec::new(),
        }
    }

    pub fn with_description(mut self, d: impl Into<String>) -> Self {
        self.description = d.into();
        self
    }

    /// Declare that valid values are multiples of `m` (e.g. `2.0` =
    /// even-only counts). The routing crate rejects non-multiples in
    /// [`crate::validate_routing_params`] before generation.
    pub fn with_multiple_of(mut self, m: f64) -> Self {
        self.multiple_of = Some(m);
        self
    }

    /// Restrict the parameter to a closed set of labelled values. The routing
    /// crate rejects any other value in [`crate::validate_routing_params`].
    pub fn with_options(mut self, options: Vec<ParamOption>) -> Self {
        self.options = options;
        self
    }
}

/// Optional structured metadata a plugin author may attach to a pattern.
#[derive(Debug, Clone, Default, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct PluginMetadata {
    /// Plugin id (registry key).
    pub id: String,
    /// Human-readable display name (may be empty during partial construction).
    pub display_name: String,
    /// Author name / handle.
    pub author: String,
    /// Semantic version of the plugin (e.g. "1.2.0").
    pub version: String,
    /// One-line description.
    pub description: String,
    /// Minimum supported copper-layer count (`None` = unconstrained).
    #[serde(default)]
    pub min_layers: Option<u32>,
    /// Maximum supported copper-layer count (`None` = unconstrained).
    #[serde(default)]
    pub max_layers: Option<u32>,
    /// The copper-layer count must be a multiple of this (e.g. `Some(2)` =
    /// even-only stacks). `None` = unconstrained.
    #[serde(default)]
    pub layers_multiple_of: Option<u32>,
}

impl PluginMetadata {
    pub fn new(id: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            ..Self::default()
        }
    }
}

/// A loadable, validated routing pattern.
///
/// Implementors produce a [`RoutingResult`] for a [`RoutingContext`]. The
/// generated result is always passed through the strict-shape [`Validator`]
/// (crate::validator) before being written or previewed; a malformed result is
/// rejected, never sanitised.
pub trait RoutingPattern: Send + Sync {
    /// Stable identifier used as the registry / config key (e.g. `"infinity-braid"`).
    fn id(&self) -> &str;

    /// Human-readable display name.
    fn display_name(&self) -> &str;

    /// Author of the plugin (defaults to empty).
    fn author(&self) -> &str {
        ""
    }

    /// Semantic version of the plugin (defaults to empty).
    fn version(&self) -> &str {
        ""
    }

    /// Optional one-line description.
    fn description(&self) -> &str {
        ""
    }

    /// Minimum supported copper-layer count. Defaults to `None` = any stack
    /// size the board provides; patterns whose geometry needs a minimum
    /// stack (e.g. a two-sided braid) override this. The host validates the
    /// context against it before generation.
    fn min_layers(&self) -> Option<u32> {
        None
    }

    /// Maximum supported copper-layer count. Defaults to `None` = no upper
    /// bound beyond the board's copper stack.
    fn max_layers(&self) -> Option<u32> {
        None
    }

    /// The copper-layer count must be a multiple of this (e.g. `Some(2)` =
    /// even-only stacks). Defaults to `None` = unconstrained.
    fn layers_multiple_of(&self) -> Option<u32> {
        None
    }

    /// The user-editable parameters this pattern exposes. Defaults to none.
    ///
    /// Derived-from-board quantities must NOT be listed here.
    fn parameters(&self) -> Vec<PatternParameter> {
        Vec::new()
    }

    /// Compose the full metadata block from the trait accessors.
    fn metadata(&self) -> PluginMetadata {
        PluginMetadata {
            id: self.id().to_string(),
            display_name: self.display_name().to_string(),
            author: self.author().to_string(),
            version: self.version().to_string(),
            description: self.description().to_string(),
            min_layers: self.min_layers(),
            max_layers: self.max_layers(),
            layers_multiple_of: self.layers_multiple_of(),
        }
    }

    /// Whether this pattern's output is expected to be a continuous path per
    /// (layer, net). Drives the validator's continuity check.
    fn expects_continuous(&self) -> bool {
        false
    }

    /// Produce the coil geometry for the given context.
    fn generate(&self, ctx: &RoutingContext) -> Result<RoutingResult, RoutingError>;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::context::RoutingContext;
    use crate::model::RoutingResult;

    /// A pattern with no metadata overrides: every layer-range field must
    /// default to `None` (unconstrained).
    struct BarePattern;

    impl RoutingPattern for BarePattern {
        fn id(&self) -> &str {
            "bare"
        }
        fn display_name(&self) -> &str {
            "Bare"
        }
        fn generate(&self, _ctx: &RoutingContext) -> Result<RoutingResult, RoutingError> {
            Ok(RoutingResult::default())
        }
    }

    /// A pattern declaring the full layer-range metadata.
    struct EvenStackPattern;

    impl RoutingPattern for EvenStackPattern {
        fn id(&self) -> &str {
            "even-stack"
        }
        fn display_name(&self) -> &str {
            "Even Stack"
        }
        fn min_layers(&self) -> Option<u32> {
            Some(2)
        }
        fn max_layers(&self) -> Option<u32> {
            Some(8)
        }
        fn layers_multiple_of(&self) -> Option<u32> {
            Some(2)
        }
        fn generate(&self, _ctx: &RoutingContext) -> Result<RoutingResult, RoutingError> {
            Ok(RoutingResult::default())
        }
    }

    #[test]
    fn layer_range_metadata_defaults_to_unconstrained() {
        let m = BarePattern.metadata();
        assert_eq!(m.min_layers, None);
        assert_eq!(m.max_layers, None);
        assert_eq!(m.layers_multiple_of, None);
    }

    #[test]
    fn layer_range_metadata_flows_into_plugin_metadata() {
        let m = EvenStackPattern.metadata();
        assert_eq!(m.min_layers, Some(2));
        assert_eq!(m.max_layers, Some(8));
        assert_eq!(m.layers_multiple_of, Some(2));
    }

    #[test]
    fn plugin_metadata_layer_fields_are_serde_defaulted() {
        // Additive change: payloads written before the layer fields existed
        // must still deserialize (serde default = unconstrained).
        let json = r#"{"id":"p","display_name":"P","author":"","version":"","description":""}"#;
        let m: PluginMetadata = serde_json::from_str(json).expect("old payload parses");
        assert_eq!(m.min_layers, None);
        assert_eq!(m.max_layers, None);
        assert_eq!(m.layers_multiple_of, None);
    }

    #[test]
    fn pattern_parameter_multiple_of_defaults_to_none() {
        let p = PatternParameter::int("n", "N", 4.0, 2.0, 8.0);
        assert_eq!(p.multiple_of, None);
        let p = PatternParameter::float("a", "A", 1.0);
        assert_eq!(p.multiple_of, None);
    }

    #[test]
    fn pattern_parameter_multiple_of_builder_and_serde_default() {
        let p = PatternParameter::int("n", "N", 4.0, 2.0, 8.0).with_multiple_of(2.0);
        assert_eq!(p.multiple_of, Some(2.0));
        // Old JSON without the field still parses (serde default).
        let json = r#"{"key":"n","label":"N","description":"","param_type":"int","default":4.0,"min":2.0,"max":8.0,"step":1.0}"#;
        let p: PatternParameter = serde_json::from_str(json).expect("old payload parses");
        assert_eq!(p.multiple_of, None);
    }
}
