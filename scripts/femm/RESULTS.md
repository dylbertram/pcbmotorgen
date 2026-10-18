# FEMM 4.2 vs the backplane model (t707)

Run on 2026-10-17 with FEMM 4.2 (x64, 22 Oct 2023 build) under Wine 8.0 on
Debian 12. To reproduce: `python3 -I scripts/femm/femm_backplane.py`. Setup is in
[README.md](README.md). No model constant was fitted to FEMM. The model numbers
come from `crates/pcbmotorgen-simulation/examples/backplane_dump.rs`.

## Setup

- The geometry is the benchmark `closed_infinity_pattern.pmmotor`: electrical
  pitch 12 mm, so τ = 6 mm and k = π/τ. Magnets are 5 × 3 mm, N44, Br 1.34 T,
  with a 0.5 mm air gap and a 1.6 mm PCB.
- The domain is 2-D planar and covers one electrical period (12 mm). The left and
  right edges are periodic, which is the infinitely long domain the model
  assumes. A = 0 sits 40 mm above and below (e^(−k·40) ≈ 10⁻⁹). All materials
  are linear, with the model's μr.
- **Inductance factor**: one sinusoidal current sheet (48 strips, 0.02 mm
  thick) per copper layer, spread evenly from the PCB bottom face to the top
  face, all carrying the same current. That is the model's own assumption.
  Each sheet is solved alone, and factor = Σ∫A·J with the stack / Σ∫A·J
  without it. This is the model's equal-weight average `1 + R·(1/N)·Σe^(−2k·d_i)`.
  "Exact 1-D" is that closed form for one slab, with
  `R = r(1−e^(−2kT))/(1−r²e^(−2kT))` and `r = (μ−1)/(μ+1)`. A second run drives
  all sheets together (see below).
- **Attraction**: the weighted-stress-tensor force on the stack from the
  alternating magnet row. Both sides are shown as force per magnet area
  (N·w·D). FEMM is planar, so the model runs with 1 m deep magnets, where its
  attraction is `R·B0²/μ0` over the footprint N·τ·D; its column is that
  pressure times τ/w. The last column is the same force measured on the
  magnets, as a numerical cross-check. The real 5 mm deep magnets are checked
  against magpylib below.
- **Peak B**: the largest |B| on a line 0.01 mm inside the stack top, against
  the model's `layer_peak_b_t` for layer 1.
- **B ratio**: By at the PCB top under a magnet centre, with the stack / without
  it. The model value is the image-magnet field on a 21-magnet, 1 m wide array,
  so it is comparable with the 2-D result.
- **100 kHz column**: a FEMM time-harmonic run with handbook conductivities
  (Al 25 MS/m, steel 6 MS/m, Si steel 2 MS/m). The skin layer is meshed at
  δ/3. The model has no eddy currents, so this column is FEMM only.
- **Mesh check** (run at f69e1ae, with the single midplane sheet; not
  repeated for the layered sheets): halving every mesh size moves the MnZn 2 mm
  sheet factor from 1.437 to 1.435, the benchmark-slice factor from 1.630 to 1.626, and the
  pressure from 45.1 to 45.1 kPa. The FR4 and no-stack rows give 1.000 ± 0.002,
  which is the numerical floor. FEMM matches the exact 1-D solution within 0.4 %
  on every single-slab row.

## Inductance factor (equal sin current sheets on the copper layers)

The model error is (model − FEMM, sheets alone) / FEMM. "model K" is the
composite reflection `R` at the PCB bottom, housing included. The model uses
two copper layers, the `backplane_dump` default.

| Stack | model K | model factor | FEMM, sheets alone | exact 1-D | model error | FEMM, sheets together | exact 1-D | FEMM 100 kHz, alone |
|---|---|---|---|---|---|---|---|---|
| No backplane | 0.000 | 1.000 | 1.000 |  | +0.0 % | 1.000 |  | 1.000 |
| FR4 1.6 mm | 0.000 | 1.000 | 1.002 | 1.000 | -0.2 % | 1.002 | 1.000 |  |
| MnZn 2 mm | 0.999 | 1.593 | 1.596 | 1.589 | -0.2 % | 1.718 | 1.710 |  |
| MnZn 5 mm | 0.999 | 1.593 | 1.596 | 1.589 | -0.2 % | 1.718 | 1.711 |  |
| Si steel 0.35 mm | 0.997 | 1.592 | 1.595 | 1.588 | -0.2 % | 1.716 | 1.709 | 1.565 |
| Flex ferrite 0.3 mm | 0.823 | 1.489 | 1.492 | 1.485 | -0.2 % | 1.592 | 1.586 |  |
| NiZn 2 mm | 0.995 | 1.591 | 1.594 | 1.586 | -0.2 % | 1.715 | 1.708 |  |
| FR4 1 mm + MnZn 2 mm | 0.351 | 1.208 | 1.211 |  | -0.2 % | 1.253 |  |  |
| MnZn 2 mm + Al 3 mm @1 mm | 0.999 | 1.593 | 1.596 |  | -0.2 % | 1.718 |  | 1.596 |
| MnZn 2 mm + steel 3 mm @1 mm | 0.999 | 1.593 | 1.596 |  | -0.2 % | 1.718 |  | 1.596 |
| Al 3 mm @1 mm (no layers) | 0.000 | 1.000 | 1.003 |  | -0.3 % | 1.003 |  | 0.829 |
| Steel 3 mm @1 mm (no layers) | 0.350 | 1.208 | 1.210 |  | -0.2 % | 1.253 |  | 1.169 |
| MnZn 1 mm + FR4 0.5 mm + MnZn 1 mm | 0.998 | 1.593 | 1.596 |  | -0.2 % | 1.717 |  |  |
| Flex ferrite 0.3 mm + Si steel 0.35 mm | 0.992 | 1.589 | 1.592 |  | -0.2 % | 1.713 |  |  |
| Flex 0.3 mm + FR4 0.2 mm + flex 0.3 mm | 0.868 | 1.515 | 1.518 |  | -0.2 % | 1.624 |  |  |

Four sheets (0, T/3, 2T/3, T) on MnZn 2 mm, model at `copper_layers = 4`:

| model factor | FEMM, sheets alone | exact 1-D | model error | FEMM, sheets together | exact 1-D |
|---|---|---|---|---|---|
| 1.521 | 1.525 | 1.519 | -0.2 % | 1.653 | 1.648 |

**Max model error against the sheets-alone runs: −0.3 %.** The midplane model
at f69e1ae was −0.3 % against its own midplane sheet. The exact 1-D columns
use the FEMM sheet centres, 0.01 mm inside each PCB face. They sit about
0.25 % below the model, which puts the sheets on the faces.

The "sheets together" runs drive all sheets at once. They include the coupling
between sheets, directly and through the image, which the model's
equal-weight average leaves out. For the fundamental alone the exact result
is `1 + R·Σ_ij e^(−k(d_i+d_j)) / Σ_ij e^(−k|d_i−d_j|)`. For two sheets that is
`1 + R·(1 + e^(−kT))/2`, 1.71–1.72 here, against the model's 1.593. The real
winding is not a pure fundamental. Its harmonics fall off faster with
distance, so the cross terms are weaker than for a pure sheet. The DXF slice
below (1.630) sits between the two.

## Attraction and field (alternating magnet row)

| Stack | model p [kPa] | FEMM p [kPa] | p error | model B ratio | FEMM B ratio | B error | FEMM p, magnet-side check [kPa] | model peak B, layer 1 [T] | FEMM peak B, stack top [T] |
|---|---|---|---|---|---|---|---|---|---|
| No backplane | 0.0 | 0.0 |  | 1.000 | 1.000 | +0.0 % | -0.0 |  |  |
| FR4 1.6 mm | 0.0 | 0.0 |  | 1.000 | 0.999 | +0.1 % | -0.7 |  |  |
| MnZn 2 mm | 45.0 | 45.1 | -0 % | 1.218 | 1.220 | -0.1 % | 45.4 | 0.557 | 0.556 |
| MnZn 5 mm | 45.0 | 45.1 | -0 % | 1.218 | 1.221 | -0.2 % | 45.4 | 0.439 | 0.439 |
| Si steel 0.35 mm | 44.9 | 45.0 | -0 % | 1.218 | 1.220 | -0.1 % | 44.7 | 2.395 | 2.402 |
| Flex ferrite 0.3 mm | 37.1 | 37.1 | -0 % | 1.180 | 1.181 | -0.1 % | 37.2 | 2.544 | 2.320 |
| NiZn 2 mm | 44.8 | 44.9 | -0 % | 1.217 | 1.219 | -0.1 % | 45.2 | 0.555 | 0.555 |
| FR4 1 mm + MnZn 2 mm | 15.8 | 15.8 | +0 % | 1.077 | 1.076 | +0.1 % | 16.1 |  |  |
| MnZn 2 mm + Al 3 mm @1 mm | 45.0 | 45.0 | -0 % | 1.218 | 1.219 | -0.1 % | 45.4 | 0.557 | 0.556 |
| MnZn 2 mm + steel 3 mm @1 mm | 45.0 | 45.0 | -0 % | 1.218 | 1.219 | -0.1 % | 45.4 | 0.557 | 0.556 |
| Al 3 mm @1 mm (no layers) | 0.0 | -0.0 |  | 1.000 | 0.999 | +0.1 % | -0.5 |  |  |
| Steel 3 mm @1 mm (no layers) | 15.8 | 15.8 | +0 % | 1.076 | 1.077 | -0.0 % | 15.3 |  |  |
| MnZn 1 mm + FR4 0.5 mm + MnZn 1 mm | 45.0 | 45.0 | -0 % | 1.218 | 1.220 | -0.2 % | 45.1 | 0.904 | 0.901 |
| Flex ferrite 0.3 mm + Si steel 0.35 mm | 44.7 | 44.7 | -0 % | 1.217 | 1.218 | -0.1 % | 44.8 | 2.779 | 0.417 |
| Flex 0.3 mm + FR4 0.2 mm + flex 0.3 mm | 39.1 | 39.2 | -0 % | 1.190 | 1.191 | -0.1 % | 39.0 | 2.607 | 1.734 |

**Max attraction error: under 1 %. Max B-ratio error: −0.2 %.** The peak-B
estimate `(1+R)·B0·coth(kT)` is within 0.3 % of FEMM on every single
high-μ plate and on the split MnZn stack. It is 10 % high for 0.3 mm flex
ferrite (μr 60) and far too high for layer 1 of the flex + steel and flex +
FR4 + flex stacks, because it assumes each layer carries all of the flux
alone. That is the conservative side for a saturation warning. At 5ffaafd
they were −85 % and −15 %. With no stack, the fundamental at the stack face is
0.2159 T in FEMM and `B0` = 0.2174 T in the model (+0.7 %). At 5ffaafd the
model used `field_at_gap`, 0.450 T.

## What changed since 5ffaafd

1. **Reflection.** `K = r·(1 − e^(−kT))` is replaced by the slab reflection
   `R = r(1 − e^(−2kT))/(1 − r²e^(−2kT))`, applied layer by layer with the
   layered-media recursion. FR4 and the housing gap are air. In linear theory a
   0.35 mm Si steel sheet reflects as fully as a thick block (R = 0.997). For
   thin sheets the linear value is an upper bound, because saturation is
   ignored. The model's estimate puts 0.35 mm Si steel (2.40 T) and 0.3 mm
   flex ferrite (2.54 T) above Bsat and warns. Until the 2026-10-17 review the
   magnetic layers were first collapsed into one slab with the series
   permeability; see below.
2. **Attraction.** The pressure is `R·B0²/μ0`, the mean Maxwell stress on a
   reflecting face. `B0 = (2/π)·Br·sin(πw/2τ)·(1 − e^(−kh))·e^(−kd)` is the
   2-D fundamental at the stack top. Since the review, finite magnet depth is
   summed over the cross-travel spectrum (below).
3. **Housing.** The housing is folded into `R` with the layered-media
   recursion instead of adding a second image. 2 mm of MnZn screens it
   completely, as FEMM shows (1.596 with or without steel). An aluminium
   housing (μr = 1) changes nothing.
4. **Saturation.** The normal field entering the stack top is `(1+R)·B0`.
   Since the review, the peak in a plate of thickness T is
   `(1+R)·B0·coth(kT)` instead of the flux over the thickness, `(1+R)·B0/(kT)`.

## Benchmark winding (DXF slice)

The 2-D slice is cut across the middle of the board (y = 3.9 mm in the DXF),
with one interior 12 mm period. The current in each conductor comes from a
resistive solve of `motor-coils_3s_0-4mm_star.dxf`, terminal to star. There are
36 conductors per period. Each carries the full ±1 A (the 3 "strands" are in
series, at a 0.667 mm pitch along x). Both layers carry current: L0 at the PCB top
and L1 at the PCB bottom, which faces the backplane. Traces are 0.2 mm (the
pmmotor `min_trace_mm`) and 35 µm thick. The excitation is line-to-line,
A = +1 A and B = −1 A, the quantity the drive model scales.

The 4-layer row copies the slice onto sheets at 0, T/3, 2T/3 and T: the L1
pattern on the lower two sheets and the L0 pattern on the upper two, each
conductor with its 2-layer current. It is one possible 4-layer winding, not a
routed board. The model columns come from `backplane_dump` ("midplane" is the
f69e1ae formula `1 + R·e^(−kT)`). The model has no yoke and no μr 1e5
material, so those rows have no model value. Error is against the L-L factor.

| Slice | layers | FEMM L-L factor | FEMM phase-A factor | model, midplane | model, layered | layered error (L-L) |
|---|---|---|---|---|---|---|
| MnZn 2 mm, L1 copper on the ferrite | 2 | 1.630 | 1.675 | 1.432 | 1.593 | -2.3 % |
| MnZn 2 mm under a 0.1 mm mask/adhesive gap | 2 | 1.511 | 1.579 | 1.389 | 1.534 | +1.5 % |
| MnZn 5 mm | 2 | 1.631 | 1.676 | 1.432 | 1.593 | -2.3 % |
| mu_r 1e5, 20 mm (one-sided limit) | 2 | 1.631 | 1.676 |  |  |  |
| MnZn 2 mm + steel yoke on the magnet backs (y = 5.1 mm) | 2 | 1.653 | 1.707 |  |  |  |
| MnZn 2 mm + mu_r 1e5 yoke 1.0 mm above the PCB | 2 | 1.969 | 2.133 |  |  |  |
| MnZn 2 mm + mu_r 1e5 yoke 0.5 mm above the PCB | 2 | 2.255 | 2.494 |  |  |  |
| MnZn 2 mm + mu_r 1e5 yoke 0.3 mm above the PCB | 2 | 2.446 | 2.723 |  |  |  |
| MnZn 2 mm, L1 copper on the ferrite | 4 | 1.549 | 1.609 | 1.432 | 1.521 | -1.8 % |

- **The earlier 1.27–1.48× target is superseded.** The model now places the
  copper on the real layer depths and is checked against FEMM at ±5 %. The old
  range is no longer a target. FEMM gives **1.63×** line-to-line on 2 mm MnZn
  when the bottom copper sits on the ferrite, and 1.51× with a 0.1 mm mask or
  adhesive gap. The layered model gives 1.593× (−2.3 %) and 1.534× (+1.5 %).
  The midplane model at f69e1ae gave 1.432× (−12 %) and 1.389× (−8 %). On the
  4-layer slice FEMM gives 1.549× and the model 1.521× (−1.8 %).
- The model gives 1.593× for 5 mm at τ = 6 mm, the same as for 2 mm.
- **In this benchmark, the backplane does not change the PWM ripple.** The drive
  model's ripple is `V/(2R)·tanh(R/(4fL))` (`drive/mod.rs:599–601`). At 100 kHz
  and L = 0.99 µH, R/(4fL) ≈ 6.3, so tanh is saturated. Ripple then depends on V
  and R, not on L. An inductance factor up to 2 moves it by less than 0.5 %. The
  formula assumes
  ±Vbus/2 across the two-phase loop (`drive/mod.rs:597–598`). If the loop sees
  the full ±Vbus, ripple doubles. That topology is unverified, and this was
  already the case before t707.
- **2.4× cannot be reached with linear material on one side.** In 2-D, the added
  inductance from one-sided material is at most the mutual inductance between the
  winding and its mirror image, which is never more than the self inductance. So
  the factor stays below 2. I have not checked that bound in 3-D. FEMM's one-sided
  limit here is 1.63× L-L (1.68× phase).
- Exceeding 2× needs magnetic material on the magnet side as well. FEMM needs
  ideal iron within about 0.3 mm above the PCB to reach 2.4× (2.45×; 0.5 mm gives
  2.26×). The moving magnets fill that space and NdFeB has μr ≈ 1.05. Back iron
  on the magnet backs, 3.5 mm above the PCB, only gives 1.65×. The backplane
  cannot close the 0.3 A ripple check (2.39 A) by itself. The drive's diagnostic
  gives two routes: 48.7 µH of series inductance per phase at 100 kHz
  (`series_inductance_h`), or a PWM of about 5.0 MHz. The DRV8311 switches up to
  200 kHz, so the PWM route is out of range.

## Review on 2026-10-17

Three model errors were fixed. No constant was fitted.

| Quantity | Before | After | Reference |
|---|---|---|---|
| Factor, MnZn 1 mm + FR4 0.5 mm + MnZn 1 mm | 1.379 (R 0.638) | 1.593 (R 0.998) | FEMM 1.596 |
| Factor, flex 0.3 mm + FR4 0.2 mm + flex 0.3 mm | 1.231 (R 0.389) | 1.515 (R 0.868) | FEMM 1.518 |
| Factor, flex 0.3 mm + Si steel 0.35 mm | 1.566 (R 0.954) | 1.589 (R 0.992) | FEMM 1.592 |
| Peak B, MnZn 2 mm | 0.415 T | 0.557 T | FEMM 0.556 T |
| Peak B, MnZn 5 mm | 0.166 T | 0.439 T | FEMM 0.439 T |
| Peak B, Si steel 0.35 mm | 2.37 T | 2.40 T | FEMM 2.40 T |
| Attraction, benchmark (5 magnets, 5 mm deep, MnZn 2 mm) | 5.63 N | 3.67 N | magpylib 3.89 N |

1. **Series permeability.** The magnetic layers were collapsed into one slab
   with `μ_eff = ΣT/Σ(T/μ)`. That is the rule for flux crossing the layers,
   but the flux runs along them. One FR4 sheet between two ferrite layers
   dropped `μ_eff` to about 5. The recursion now runs over every layer.
   Single-slab stacks and FR4 above the first magnetic layer give the same
   numbers as before.
2. **Peak B.** `(1+R)·B0/(kT)` is the mean over the thickness. The field
   decays into the plate as `cosh`, so the top face carries
   `(1+R)·B0·coth(kT)`. The old value was low by 25 % for 2 mm MnZn and
   by 62 % for 5 mm.
3. **Attraction.** `R·B0²/μ0·N·τ·D` is the 2-D value. With D = 5 mm
   ≈ τ, the field spreads across the magnet edges and the real pull is lower.
   The model now sums `R(κ)·B(κ)²/μ0` over the cross-travel spectrum
   `2·sin(k_y·D/2)/k_y` of the magnets (κ² = k² + k_y²). It reduces to the 2-D
   value for deep magnets.

### Magpylib checks (magpylib 5.2.3)

- magba and magpylib give the same Bz, to 2·10⁻¹⁶ T, at z = 0, −0.8 and
  −1.6 mm, for the bare array and for the array with its R-scaled images,
  both for 21 magnets 1 m deep and for 5 magnets 5 mm deep.
- On the 21 × 1 m array the fundamental of Bz matches `B0` exactly: 0.2174 T
  at the stack top and 0.5024 T at the PCB top. The harmonics at the stack top
  are B3/B1 = 0.034 and B5/B1 = 0.001 (0.181 and 0.024 at the PCB top).
- For the real 5 mm deep magnets B1 at the stack top is 0.1926 T on the
  centre line, 11 % below the 2-D `B0`. `b0_t` and the peak-B estimate keep
  the 2-D value, which is the conservative side.
- Attraction, force between the magnets and their R-scaled images
  (R = 0.999), integrated over the magnet faces:

| Magnets | magpylib 3-D | model | 2-D formula |
|---|---|---|---|
| 21, 1 m deep | 4753 N | 4724 N (−0.6 %) | 4733 N |
| 5, 1 m deep | 1148 N | 1125 N (−2.0 %) | 1127 N |
| 5, 5 mm deep | 3.89 N | 3.67 N (−5.6 %) | 5.63 N |
| 10, 5 mm deep | 7.56 N | 7.34 N (−3.0 %) | 11.27 N |
| 5, 10 mm deep | 9.73 N | 9.27 N (−4.7 %) | 11.27 N |
| 5, 20 mm deep | 21.3 N | 20.5 N (−3.5 %) | 22.5 N |

  The remaining few percent are the array ends, which the model ignores.
- Field boost from the images, fundamental of Bz, 5 mm deep magnets: 1.134×
  at the PCB top and 1.999× at the stack top (1.187× and 1.999× for the 2-D
  array). The force sweep sees this boost through the image magnets; no
  second R-based factor is applied to K_f.

### 3-D image check of the inductance factor

The routed benchmark winding (the `closed_infinity_user_project_diagnostics`
fixture) was mirrored across a μ→∞ plane 17.5 µm below the L1 copper, using
the partial-inductance filaments of `drive/inductance.rs`. This was a one-off
scratch run, not part of the harness. L-L factor in 3-D: **1.523**. The model
gives 1.593 and the 2-D FEMM slice 1.630. With the plane 0.1 mm lower: 3-D
1.378, model 1.534, FEMM 1.511. The 2-D numbers treat the conductors as
infinitely long. The real ones cross an 8 mm active width and have end turns,
so the coupling to the image is weaker.

## Remaining limits of `backplane/mod.rs`

- The inductance factor averages `N = num_layers` copper sheets spread
  evenly from the PCB bottom to the top, all with the same current (a
  series-connected coil). Real 4- and 6-layer stackups have uneven core and
  prepreg thicknesses, so the inner-layer depths are approximate. The average
  leaves out the coupling between layers. A pure-fundamental sheet set with
  that coupling gives 1.718× (2 sheets) against the model's 1.593×. The real
  winding has harmonics that weaken it, so it lands between the two
  (1.630×).
- The inductance factor is 2-D. For the benchmark winding a 3-D image
  estimate gives 1.52× against the model's 1.59× (copper on the ferrite) and
  1.38× against 1.53× (0.1 mm gap). Treat the model as an upper estimate of
  about 5–10 % for short active widths.
- Only the fundamental is modelled. The image magnets use the fundamental `R`
  for every harmonic, which is good for the field ratio here (−0.2 %).
- Eddy currents are not modelled. At the 100 kHz PWM, a 3 mm aluminium
  housing 1 mm below a bare PCB cuts inductance by 17 % (0.829×, sheets
  alone), and the model reports 1.000×. Behind 2 mm of MnZn the effect is gone.
  Linear FEMM keeps 0.35 mm Si steel at 1.565× at 100 kHz (1.592× static), because μr = 4000 dominates the
  skin effect. Real lamination permeability and loss at 100 kHz are far worse
  than this linear run, so the model's Si steel warning stays.
- Every FEMM run is linear. The peak-B column checks where saturation would
  start, not what happens after it, so the thin-sheet rows (Si steel, flex
  ferrite) are upper bounds. The next step is a nonlinear
  FEMM run with the magnets present and a B-H curve, using FEMM's
  incremental-permeability solve for the coil inductance.
- `attraction_n` is reported but does not yet load the bearing in the
  friction budget (`FrictionEstimator::from_config` uses zero normal force).
