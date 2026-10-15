use super::runtime_registry::{bundled_registry, runtime};

/// Look up a pattern's declared user-editable parameters by id (bundled or
/// runtime-loaded). Returns an empty vec if the id is unknown.
pub fn pattern_parameters(id: &str) -> Vec<crate::PatternParameter> {
    if let Ok(guard) = runtime().lock() {
        if let Some(p) = guard.get(id) {
            return p.parameters();
        }
    }
    let reg = bundled_registry();
    match reg.get(id) {
        Some(p) => p.parameters(),
        None => Vec::new(),
    }
}

/// Look up a pattern's full metadata block (author/version/description) by id.
pub fn pattern_metadata(id: &str) -> Option<crate::PluginMetadata> {
    if let Ok(guard) = runtime().lock() {
        if let Some(p) = guard.get(id) {
            return Some(p.metadata());
        }
    }
    let reg = bundled_registry();
    reg.get(id).map(|p| p.metadata())
}

/// Validate a pattern id against its declared parameter schema, clamping /
/// rejecting out-of-range values. Returns a helpful error on the first bad
/// parameter.
pub fn validate_routing_params(
    id: &str,
    params: &std::collections::HashMap<String, f64>,
) -> Result<(), String> {
    let schema = pattern_parameters(id);
    if schema.is_empty() {
        return Ok(());
    }
    for p in &schema {
        if let Some(v) = params.get(&p.key) {
            if !v.is_finite() {
                return Err(format!(
                    "{} = {} is not finite for pattern \"{id}\" — use a finite number",
                    p.label, v
                ));
            }
            if matches!(p.param_type, crate::ParamType::Int)
                && (v.round() - *v).abs() > 1e-9
            {
                return Err(format!(
                    "{} = {} is not an integer for pattern \"{id}\"",
                    p.label, v
                ));
            }
            if let Some(min) = p.min {
                if *v < min - 1e-9 {
                    return Err(format!(
                        "{} = {} is below the minimum {} for pattern \"{id}\"",
                        p.label, v, min
                    ));
                }
            }
            if let Some(max) = p.max {
                if *v > max + 1e-9 {
                    return Err(format!(
                        "{} = {} exceeds the maximum {} for pattern \"{id}\"",
                        p.label, v, max
                    ));
                }
            }
            if let Some(mult) = p.multiple_of {
                // Same epsilon discipline as the min/max checks: values that
                // land within 1e-9 of a valid multiple pass (float noise).
                if mult.is_finite() && mult > 0.0 {
                    let scaled = v / mult;
                    if (scaled.round() - scaled).abs() * mult > 1e-9 {
                        return Err(format!(
                            "{} = {} is not a multiple of {} for pattern \"{id}\"",
                            p.label, v, mult
                        ));
                    }
                }
            }
            if !p.options.is_empty() && !p.options.iter().any(|o| (o.value - v).abs() <= 1e-9) {
                let allowed: Vec<String> = p
                    .options
                    .iter()
                    .map(|o| format!("{} ({})", o.value, o.label))
                    .collect();
                return Err(format!(
                    "{} = {} is not one of the allowed values [{}] for pattern \"{id}\"",
                    p.label,
                    v,
                    allowed.join(", ")
                ));
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::context::RoutingContext;
    use crate::model::RoutingResult;
    use crate::pattern::{PatternParameter, RoutingPattern};
    use std::collections::HashMap;
    use std::sync::atomic::{AtomicU64, Ordering};

    /// Register a scratch pattern under a unique id and validate a single
    /// param value against it. Unique ids keep the global runtime registry
    /// race-free across parallel tests (same discipline as the `SCRATCH_SEQ`
    /// ids in the dispatch tests — a key/value-derived id collides whenever
    /// two tests validate the same value, and registration replaces by id).
    fn validate_value(params: Vec<PatternParameter>, key: &str, value: f64) -> Result<(), String> {
        static SCRATCH_SEQ: AtomicU64 = AtomicU64::new(0);
        struct Scratch {
            id: String,
            params: Vec<PatternParameter>,
        }
        impl RoutingPattern for Scratch {
            fn id(&self) -> &str {
                &self.id
            }
            fn display_name(&self) -> &str {
                "Scratch"
            }
            fn parameters(&self) -> Vec<PatternParameter> {
                self.params.clone()
            }
            fn generate(
                &self,
                _ctx: &RoutingContext,
            ) -> Result<RoutingResult, crate::error::RoutingError> {
                Ok(RoutingResult::default())
            }
        }
        let id = format!(
            "scratch-{}-{}-{}",
            SCRATCH_SEQ.fetch_add(1, Ordering::Relaxed),
            params.first().map(|p| p.key.as_str()).unwrap_or("x"),
            value
        )
        .replace('.', "_");
        crate::register_runtime_pattern(Box::new(Scratch { id: id.clone(), params }))
            .map_err(|e| format!("register failed: {e}"))?;
        let mut map = HashMap::new();
        map.insert(key.to_string(), value);
        let res = validate_routing_params(&id, &map);
        crate::unregister_runtime_pattern(&id);
        res
    }

    #[test]
    fn multiple_of_accepts_valid_multiples() {
        let params =
            vec![PatternParameter::int("n", "Strands", 4.0, 2.0, 12.0).with_multiple_of(2.0)];
        assert_eq!(validate_value(params.clone(), "n", 4.0), Ok(()));
        assert_eq!(validate_value(params.clone(), "n", 2.0), Ok(()));
        assert_eq!(validate_value(params, "n", 12.0), Ok(()));
    }

    #[test]
    fn multiple_of_rejects_non_multiples() {
        let params =
            vec![PatternParameter::int("n", "Strands", 4.0, 2.0, 12.0).with_multiple_of(2.0)];
        let err = validate_value(params, "n", 3.0).unwrap_err();
        assert!(err.contains("not a multiple of 2"), "unexpected error: {err}");
    }

    #[test]
    fn multiple_of_allows_epsilon_close_values() {
        // Same 1e-9 discipline as the min/max checks: float noise passes.
        let params =
            vec![PatternParameter::int("n", "Strands", 4.0, 2.0, 12.0).with_multiple_of(2.0)];
        assert_eq!(validate_value(params, "n", 4.0 + 5e-10), Ok(()));
    }

    #[test]
    fn multiple_of_works_for_float_params() {
        let params = vec![
            PatternParameter::float("angle", "Angle", 1.5)
                .with_description("degrees")
                .with_multiple_of(0.5),
        ];
        assert_eq!(validate_value(params.clone(), "angle", 2.5), Ok(()));
        assert_eq!(validate_value(params.clone(), "angle", 0.0), Ok(()));
        let err = validate_value(params, "angle", 1.3).unwrap_err();
        assert!(err.contains("not a multiple of 0.5"), "unexpected: {err}");
    }

    #[test]
    fn unset_multiple_of_is_unconstrained() {
        let params = vec![PatternParameter::int("n", "Strands", 4.0, 2.0, 12.0)];
        assert_eq!(validate_value(params, "n", 3.0), Ok(()));
    }

    #[test]
    fn degenerate_multiple_of_is_ignored() {
        // A pattern declaring multiple_of = 0 / NaN must not panic or reject
        // everything; the constraint is simply skipped.
        let mut zero = PatternParameter::int("n", "Strands", 4.0, 2.0, 12.0);
        zero.multiple_of = Some(0.0);
        assert_eq!(validate_value(vec![zero], "n", 3.0), Ok(()));
        let mut nan = PatternParameter::int("m", "Strands", 4.0, 2.0, 12.0);
        nan.multiple_of = Some(f64::NAN);
        assert_eq!(validate_value(vec![nan], "m", 3.0), Ok(()));
    }

    #[test]
    fn multiple_of_composes_with_min_max() {
        // Out-of-range values still trip the min/max checks.
        let params =
            vec![PatternParameter::int("n", "Strands", 4.0, 2.0, 12.0).with_multiple_of(2.0)];
        let err = validate_value(params.clone(), "n", 1.0).unwrap_err();
        assert!(err.contains("below the minimum"), "unexpected: {err}");
        let err = validate_value(params, "n", 14.0).unwrap_err();
        assert!(err.contains("exceeds the maximum"), "unexpected: {err}");
    }

    #[test]
    fn param_type_int_still_enforced_alongside_multiple_of() {
        let p = PatternParameter::int("n", "Strands", 4.0, 2.0, 12.0).with_multiple_of(2.0);
        // 3.5 satisfies no useful multiple and is not an integer — int-ness
        // fires first.
        let err = validate_value(vec![p], "n", 3.5).unwrap_err();
        assert!(err.contains("not an integer"), "unexpected: {err}");
    }

    #[test]
    fn options_restrict_values_to_the_declared_set() {
        use crate::pattern::ParamOption;
        let p = PatternParameter::int("mode", "Mode", 0.0, 0.0, 4.0).with_options(vec![
            ParamOption::new(0.0, "Off"),
            ParamOption::new(2.0, "On"),
        ]);
        assert_eq!(validate_value(vec![p.clone()], "mode", 2.0), Ok(()));
        let err = validate_value(vec![p], "mode", 1.0).unwrap_err();
        assert!(err.contains("not one of the allowed values"), "unexpected: {err}");
    }
}
