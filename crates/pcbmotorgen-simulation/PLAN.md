# Scope, Bugs & TODO

---

## Deferred

The following features are explicitly **out of scope for now** and tracked here to prevent accidental implementation.

| #   | Deferral                               | Notes                                                                                                                                                                                                                                                                                                                                          |
| --- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D2  | Proper Halbach model                   | REMOVED — the magnet arrangement options (Halbach and back-iron variants) were removed from the product scope so the mover is always the plain alternating array. The old single X-polarised interleave-per-gap approximation and the method-of-images back iron live in git history. |

---

## Resolved

| #  | Item                                        | Resolution                                                                                                                                                                                                                                                                                                                              |
| --- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1 | FOC rewrite (former D1, kata p10y)          | RESOLVED — the commutation law is documented as the glossary-normative FOC with the **pinned d-axis convention**: `id = 0`, pure q-axis (product-owner approved; the 90° rule = q-axis current only). The mathematics was already the q-axis law — the "legacy" framing and all `TODO: FOC-rewrite-pcb-motor-expert` markers were removed from `src/magnetic/force_eval/{commutation,mod}.rs`. Vernier support kept via `phase_band_pitch_m`; the balanced 120° law is pinned as the 2τ_p/3 special case (`test_balanced_120deg_law_special_case`). The 3-point guard stays as the live self-calibration. |
| R2 | FOC ripple closed-form bounds (former D4)   | SUPERSEDED — the `#[ignore]`d `test_foc_rewrite_ripple_target_*` placeholders awaited a closed-form ripple bound from an FOC spec that was superseded by the pinned `id = 0` convention. Removed; thrust-optimality of the implemented alignment is pinned empirically instead by `test_foc_thrust_peaks_at_zero_phase_tilt` (phase-tilt sweep δ ∈ [−90°, +90°] through the real force sweep, mean thrust peaks at δ = 0). |

---

## Known Issues (Active Bugs)

This is the consolidated, high-level bug tracker. **All currently ACTIVE bugs are
tracked in the round sections below**

| #   | Bug | Status | Notes |
| --- | --- | ------ | ----- |

---

## Wishes (Deferred / Backlog)

Improvements the user has requested but deferred to a future round.

| #   | Wish                           | Effort | Notes                                                                                                                                                                                                                                        |
| --- | ------------------------------ | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| W1  | FOC error-injection test hooks | Medium | Add a `foc_variant: FocVariant` field / `phase_offset_override` to `ForceEvaluator` so the 3-point guard can be unit-tested against a 90° sin error and a wrong per-coil offset. These fault-rejection cases are not currently covered; see `src/magnetic/force_eval/mod.rs`. |

---
