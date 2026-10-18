# FEMM 4.2 vs the backplane model (t707)

Run on 2026-10-18 with FEMM 4.2 (x64, 22 Oct 2023 build) under Wine 8.0 on
Debian 12, from a fresh work directory. To reproduce:
`python3 -I scripts/femm/femm_backplane.py` (about 25 min). Setup is in
[README.md](README.md). No model constant was fitted to FEMM. The model numbers
come from `crates/pcbmotorgen-simulation/examples/backplane_dump.rs`. The
saturation and eddy-current checks (tickets 04n2, q9nw) are in their own
section, [Saturation and eddy currents](#saturation-and-eddy-currents-2026-10-18).

## Setup

- The geometry is the benchmark `closed_infinity_pattern.pmmotor`: electrical
  pitch 12 mm, so τ = 6 mm and k = π/τ. Magnets are 5 × 3 mm, N44, Br 1.34 T,
  with a 0.5 mm air gap and a 1.6 mm PCB.
- The domain is 2-D planar and covers one electrical period (12 mm). The left and
  right edges are periodic, which is the infinitely long domain the model
  assumes. A = 0 sits 40 mm above and below (e^(−k·40) ≈ 10⁻⁹). Up to the
  benchmark slice all materials are linear, with the model's μr (flexible
  ferrite 130 since 2026-10-18), and the model runs with saturation off.
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
  the model's linear peak (`linear_peak_b_t`) for layer 1.
- **B ratio**: By at the PCB top under a magnet centre, with the stack / without
  it. The model value is the image-magnet field on a 21-magnet, 1 m wide array,
  so it is comparable with the 2-D result.
- **100 kHz column**: a FEMM time-harmonic run with the model's conductivities
  (Al 6061 25 MS/m, steel 1018 5.8 MS/m, Si steel 2 MS/m, MnZn 0.2 S/m). The
  skin layer is meshed at δ/3. The model's values are in the coil table of
  the saturation and eddy-current section.
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
| Flex ferrite 0.3 mm | 0.910 | 1.540 | 1.543 | 1.536 | -0.2 % | 1.654 | 1.647 |  |
| NiZn 2 mm | 0.995 | 1.591 | 1.594 | 1.586 | -0.2 % | 1.715 | 1.708 |  |
| FR4 1 mm + MnZn 2 mm | 0.351 | 1.208 | 1.211 |  | -0.2 % | 1.253 |  |  |
| MnZn 2 mm + Al 3 mm @1 mm | 0.999 | 1.593 | 1.596 |  | -0.2 % | 1.718 |  | 1.596 |
| MnZn 2 mm + steel 3 mm @1 mm | 0.999 | 1.593 | 1.596 |  | -0.2 % | 1.718 |  | 1.596 |
| Al 3 mm @1 mm (no layers) | 0.000 | 1.000 | 1.003 |  | -0.3 % | 1.003 |  | 0.829 |
| Steel 3 mm @1 mm (no layers) | 0.350 | 1.208 | 1.210 |  | -0.2 % | 1.253 |  | 1.169 |
| MnZn 1 mm + FR4 0.5 mm + MnZn 1 mm | 0.998 | 1.593 | 1.596 |  | -0.2 % | 1.717 |  |  |
| Flex ferrite 0.3 mm + Si steel 0.35 mm | 0.995 | 1.591 | 1.594 |  | -0.2 % | 1.715 |  |  |
| Flex 0.3 mm + FR4 0.2 mm + flex 0.3 mm | 0.928 | 1.551 | 1.554 |  | -0.2 % | 1.667 |  |  |

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
| MnZn 2 mm | 45.0 | 45.1 | -0 % | 1.218 | 1.220 | -0.1 % | 45.4 | 0.556 | 0.556 |
| MnZn 5 mm | 45.0 | 45.1 | -0 % | 1.218 | 1.221 | -0.2 % | 45.4 | 0.439 | 0.439 |
| Si steel 0.35 mm | 44.9 | 45.0 | -0 % | 1.218 | 1.220 | -0.1 % | 44.7 | 2.392 | 2.402 |
| Flex ferrite 0.3 mm | 41.0 | 41.0 | -0 % | 1.199 | 1.200 | -0.1 % | 41.2 | 2.542 | 2.557 |
| NiZn 2 mm | 44.8 | 44.9 | -0 % | 1.217 | 1.219 | -0.1 % | 45.2 | 0.555 | 0.555 |
| FR4 1 mm + MnZn 2 mm | 15.8 | 15.8 | +0 % | 1.077 | 1.076 | +0.1 % | 16.1 |  |  |
| MnZn 2 mm + Al 3 mm @1 mm | 45.0 | 45.0 | -0 % | 1.218 | 1.219 | -0.1 % | 45.4 | 0.556 | 0.556 |
| MnZn 2 mm + steel 3 mm @1 mm | 45.0 | 45.0 | -0 % | 1.218 | 1.219 | -0.1 % | 45.4 | 0.556 | 0.556 |
| Al 3 mm @1 mm (no layers) | 0.0 | -0.0 |  | 1.000 | 0.999 | +0.1 % | -0.5 |  |  |
| Steel 3 mm @1 mm (no layers) | 15.8 | 15.8 | +0 % | 1.076 | 1.077 | -0.0 % | 15.3 |  |  |
| MnZn 1 mm + FR4 0.5 mm + MnZn 1 mm | 45.0 | 45.0 | -0 % | 1.218 | 1.220 | -0.2 % | 45.1 | 0.902 | 0.901 |
| Flex ferrite 0.3 mm + Si steel 0.35 mm | 44.8 | 44.9 | -0 % | 1.217 | 1.219 | -0.1 % | 44.9 | 0.434 | 0.418 |
| Flex 0.3 mm + FR4 0.2 mm + flex 0.3 mm | 41.8 | 41.9 | -0 % | 1.203 | 1.204 | -0.1 % | 41.7 | 2.042 | 2.058 |

**Max attraction error: under 1 %. Max B-ratio error: −0.2 %.** Since
2026-10-18 the linear peak is the in-plane field on the faces of each layer
from the layered solution, not the single-plate `(1+R)·B0·coth(kT)`. It is
within 0.6 % of FEMM on every single plate and within 4 % on layer 1 of the
multi-layer stacks (flex + Si steel: 0.434 T against FEMM's 0.418 T, where the
single-plate estimate gave 2.78 T). With no stack, the fundamental at the stack
face is 0.2159 T in FEMM and `B0` = 0.2174 T in the model (+0.7 %). At 5ffaafd
the model used `field_at_gap`, 0.450 T.

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
  model's ripple is `V/(2R)·tanh(R/(4fL))` (the ripple block of
  `drive/mod.rs`, which since 2026-10-18 takes L at the PWM frequency). At
  100 kHz and L = 0.99 µH, R/(4fL) ≈ 6.3, so tanh is saturated. Ripple then
  depends on V and R, not on L. An inductance factor up to 2 moves it by less
  than 0.5 %. The formula assumes ±Vbus/2 across the two-phase loop. If the
  loop sees the full ±Vbus, ripple doubles. That topology is unverified, and
  this was already the case before t707.
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

Three model errors were fixed. No constant was fitted. Flexible ferrite had
μr 60 at the time.

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

## Saturation and eddy currents (2026-10-18)

Tickets 04n2 and q9nw. The user's "version 2" of the benchmark has a 0.8 mm
PCB, one 0.2 mm flexible ferrite sheet under it and a 1 mm aluminium 6061
housing 0.1 mm below the sheet; 12 V, 1 A, DRV8311 at 100 kHz, target speed
20 m/s. The app showed "Layer 1, Flexible ferrite sheet 5.57 T peak" with a
warning to add thickness, and kept using the linear sheet for K_f, the
inductance and the attraction. The warning was right that the sheet
saturates. The 5.57 T was the linear model's demand, not a field that can
exist, and every number downstream used an unsaturated sheet.

### What the model does now

The module docs of `crates/pcbmotorgen-simulation/src/backplane/mod.rs` give
the equations and conventions (`e^(jωt)`, `R > 0` magnetic, `R → −1` perfect
conductor). In short:

- **Saturation (magnet field).** Each soft-magnetic layer follows a
  two-slope curve, `B = μ0·H + clip(μ0(μi − 1)·H, ±Bsat)`. The fundamental
  sees its describing-function permeability `μ_eff` at the layer's mean
  in-plane field, solved as a fixed point. Layers whose linear field reaches
  Bsat on a face are split into sublayers (`k·T ≤ 0.1`), so a thick plate can
  saturate near its face only. The saturated `R` drives the image magnets
  (K_f) and the attraction.
- **Coil field under the magnets.** The small-signal in-plane permeability
  is the differential one along the bias (`μi` below the knee, 1 above) and
  the secant one `B/(μ0·|H|)` across it, as for any isotropic saturating
  material, averaged harmonically over a pole pitch. Away from the magnets
  the sheet keeps `μi`. The two are weighted by `N·τ / active_area_length`
  (0.33 for version 2).
- **Eddy currents.** The layered recursion takes `γ = √(κ² + jωμ0μσ)` and
  `η = γ/μ`. The coil factor `F = 1 + R·(1/N)·Σe^(−2k·d_i)` gives
  `L = L0·Re F` and `ΔR = −ωL0·Im F`. In the stator frame the magnets are a
  travelling wave at `ω = k·v`. Each mode presses with `Re R·B²/μ0` and drags
  with `−(k/κ)·Im R·B²/μ0`, summed over the cross-travel spectrum as for the
  attraction. With `σ = 0` everything reduces bit for bit to the static model.
- **Materials.** Flexible ferrite sheets are sintered NiZn, cracked for
  flexibility: μr 130 (Laird MULL12060-200: μ' ≈ 135 from 1 to 10 MHz, 150 at
  13.56 MHz; Laird MHLL 130; Würth WE-FSFS 364001 110 at 1 MHz). None of these
  datasheets gives Bsat; bulk NiZn of the same μi gives 0.24–0.25 T (Fair-Rite
  61, μi 125, at 1.2 kA/m) to 0.31 T (Ferroxcube 4M2, μi 140), so 0.25 T stays.
  The default thickness is now 0.1 mm, the ferrite of the common sheets. The
  Laird sheet the user cites has 0.10 mm of ferrite in its 0.20 mm total, so
  the design's 0.2 mm counts the adhesive and cover tape as ferrite.
  Conductivities: Al 6061-T6 25 MS/m, 5052 20 MS/m, 1018 5.8 MS/m, 304
  1.39 MS/m, 316 1.35 MS/m, 430 1.67 MS/m, Si steel 2 MS/m, MnZn 0.2 S/m,
  NiZn and flex sheets 0. Layers take datasheet μr and Bsat overrides.

### Version 2, before and after

From `closed_infinity_version_two_diagnostics` (force sweep at mesh 20 on the
routed copper) and `backplane_dump`.

| Quantity | Before (e02d2ec, μr 60) | After | Note |
|---|---|---|---|
| Sheet state | "5.57 T peak" | saturated, 22× the flux it carries at Bsat; peak 0.56 T at the solved state | linear demand 5.5 T |
| Effective μr of the sheet | 60 (linear) | 2.07 for the magnets, 1.33 for the coil under them, 130 elsewhere | |
| R (image strength) | 0.758 | 0.073 | linear with μr 130: 0.871 |
| K_f = mean thrust at 1 A | 0.0998 N | 0.0715 N | bare 0.8 mm PCB: 0.0684 N |
| Attraction at standstill | 7.74 N | 0.84 N | 0.61 N at 20 m/s |
| Inductance factor, low frequency | 1.543 | 1.427 | 1.624 away from the magnets, 1.019 under them |
| Inductance factor at 100 kHz | (none) | 1.285 | 1.619 away, 0.595 under them |
| L_s, low frequency / at 100 kHz | 1.561 µH / (none) | 1.444 µH / 1.300 µH | bare 0.8 mm PCB: 1.012 µH |
| Eddy resistance at 100 kHz | (none) | 14.7 mΩ per phase | phase R 2.47 Ω |
| PWM ripple (50 % duty estimate) | 2.431 A | 2.432 A | R/(4fL) ≈ 4.7, tanh saturated |
| Eddy loss in the housing from the ripple | (none) | 0.037 W | |
| Eddy drag at 1 m/s | (none) | 0.046 N, 0.046 W | 64 % of the thrust |
| Eddy drag at 20 m/s | (none) | 0.86 N, 17.2 W | 12× the thrust |
| Speed at which drag equals the full-current thrust | (none) | 1.56 m/s | |
| Line voltage at 20 m/s | 6.79 V | 6.13 V | lower K_f, lower back-EMF |
| Thickness to carry the flux | "add thickness" | at least 5.0 mm of this sheet, or 2.8 mm of MnZn | lower bounds, see below |

The sheet adds 4 % to K_f, not the 46 % the linear model claimed. The
aluminium housing is the larger problem: at the target speed its eddy drag is
twelve times the thrust, and at 1 A the mover cannot get past about 1.6 m/s.
The saturated sheet lets the magnet field straight through to the housing.

### FEMM setup for this section

- Geometry as above with the 0.8 mm PCB unless noted; magnets 1 m deep (2-D);
  the model runs with the same geometry and the winding all under the
  magnets.
- Nonlinear runs use `B = μ0·H + Bsat·tanh(μ0(μi − 1)·H/Bsat)`: the model's
  initial μ and Bsat with a rounded knee, as real ferrite has. A second set
  uses the model's own two-slope curve.
- Incremental inductance: the magnet bias is solved nonlinearly with the coil
  sheets present at zero current. Each sheet is then solved alone with FEMM's
  incremental permeability of that state (`mi_setprevious`, type 1) and the
  magnets switched off, and compared with the same sheet with no stack. The
  coil sheet `cos(kx − φ)` is run at two positions relative to the magnets:
  φ = 0 puts its in-plane flux where the bias is in-plane (saturated), φ = π/2
  where the bias is normal.
- 100 kHz: the two coil sheets solved alone, time-harmonic, complex `Σ∫A·J`
  with the stack over the same without it.
- Drag: one travelling current sheet `J0·e^(−jkx)` (strips with `cos kx` and
  `−sin kx` parts) at the PCB top, at `f = v/(2τ)`. The time-averaged weighted
  stress tensor force on the stack and housing, per `B0²/μ0` per period, is
  compared with `−Im R` (x) and `Re R` (y), `B0` being the bare travelling
  field at the stack top. The last column checks FEMM's own energy balance,
  resistive loss over `F·v`.
- Tolerances as guidance: ±5 % for inductance and field ratio, ±10 % for
  forces and flux densities. Nothing was tuned to them.

#### Saturation: field and attraction (0.8 mm PCB, magnet row, 1 m deep)

| Stack | model R, linear | model R, saturated | model B ratio | FEMM B ratio, nonlinear | B ratio error | | model B ratio, linear | FEMM B ratio, linear | model p [kPa] | FEMM p, nonlinear [kPa] | p error | | model p, linear [kPa] | FEMM p, linear [kPa] |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Flex ferrite 0.1 mm | 0.773 | 0.037 | 1.018 | 1.027 | -0.9 % | pass | 1.157 | 1.388 | 3.9 | 3.7 | +5.8 % | pass | 33.2 | 81.0 |
| Flex ferrite 0.2 mm (version 2) | 0.871 | 0.073 | 1.036 | 1.051 | -1.4 % | pass | 1.306 | 1.439 | 7.6 | 7.2 | +5.6 % | pass | 64.6 | 91.3 |
| Flex ferrite 1 mm | 0.969 | 0.314 | 1.155 | 1.170 | -1.3 % | pass | 1.478 | 1.489 | 32.7 | 30.6 | +6.9 % | pass | 100.9 | 101.5 |
| Flex ferrite 5 mm | 0.985 | 0.959 | 1.473 | 1.305 | +12.9 % | FAIL | 1.486 | 1.497 | 99.9 | 65.8 | +51.9 % | FAIL | 102.5 | 103.1 |
| MnZn 2 mm | 0.999 | 0.920 | 1.454 | 1.413 | +2.9 % | pass | 1.493 | 1.503 | 95.8 | 84.4 | +13.5 % | FAIL | 104.0 | 104.6 |
| MnZn 2.8 mm | 0.999 | 0.999 | 1.493 | 1.453 | +2.8 % | pass | 1.493 | 1.503 | 104.0 | 97.6 | +6.6 % | pass | 104.1 | 104.6 |

#### Saturation: flux density in the layer

| Stack | model flux overload | model mu_eff | model mean in-plane B1 [T] | FEMM Bx1 at mid-layer [T] | error | | model peak [T] | FEMM peak, 0.01 mm inside the face [T] | error | | model linear peak [T] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Flex ferrite 0.1 mm | 39.02 | 2.0 | 0.632 | 0.599 | +5.5 % | pass | 0.568 | 0.600 | -5.2 % | pass | 9.77 |
| Flex ferrite 0.2 mm (version 2) | 22.01 | 2.1 | 0.616 | 0.583 | +5.7 % | pass | 0.556 | 0.589 | -5.6 % | pass | 5.52 |
| Flex ferrite 1 mm | 4.90 | 2.7 | 0.510 | 0.472 | +8.1 % | pass | 0.477 | 0.516 | -7.6 % | pass | 1.34 |
| Flex ferrite 5 mm | 1.00 | 100.4 | 0.247 | 0.214 | +15.3 % | FAIL | 0.647 | 0.482 | +34.3 % | FAIL | 0.66 |
| MnZn 2 mm | 1.40 | 32.9 | 0.591 | 0.539 | +9.7 % | pass | 0.634 | 0.554 | +14.5 % | FAIL | 0.85 |
| MnZn 2.8 mm | 1.00 | 2295.3 | 0.450 | 0.455 | -1.0 % | pass | 0.661 | 0.571 | +15.6 % | FAIL | 0.73 |

#### Saturation with the model's two-slope B-H curve in FEMM

| Stack | model B ratio | FEMM B ratio | error | | model p [kPa] | FEMM p [kPa] | error | | model mean in-plane B1 [T] | FEMM Bx1 at mid-layer [T] | error | |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Flex ferrite 0.1 mm | 1.018 | 1.027 | -0.9 % | pass | 3.9 | 3.7 | +5.8 % | pass | 0.632 | 0.599 | +5.5 % | pass |
| Flex ferrite 0.2 mm (version 2) | 1.036 | 1.051 | -1.4 % | pass | 7.6 | 7.2 | +5.6 % | pass | 0.616 | 0.583 | +5.7 % | pass |
| Flex ferrite 1 mm | 1.155 | 1.170 | -1.3 % | pass | 32.7 | 30.6 | +6.9 % | pass | 0.510 | 0.472 | +8.1 % | pass |
| Flex ferrite 5 mm | 1.473 | 1.305 | +12.9 % | FAIL | 99.9 | 65.9 | +51.6 % | FAIL | 0.247 | 0.244 | +1.2 % | pass |
| MnZn 2 mm | 1.454 | 1.413 | +2.9 % | pass | 95.8 | 84.4 | +13.5 % | FAIL | 0.591 | 0.540 | +9.5 % | pass |
| MnZn 2.8 mm | 1.493 | 1.453 | +2.7 % | pass | 104.0 | 97.6 | +6.6 % | pass | 0.450 | 0.475 | -5.2 % | pass |

#### Inductance under the magnets (incremental permeability, 0.8 mm PCB)

| Stack | model mu_inc | model factor under the magnets | FEMM, coil flux on the saturated regions | FEMM, coil flux on the unsaturated regions | FEMM mean | error vs mean | | model factor away from the magnets |
|---|---|---|---|---|---|---|---|---|
| Flex ferrite 0.2 mm (version 2) | 1.33 | 1.019 | 1.004 | 1.060 | 1.032 | -1.2 % | pass | 1.624 |
| Flex ferrite 1 mm | 1.46 | 1.088 | 1.012 | 1.229 | 1.121 | -3.0 % | pass | 1.694 |
| MnZn 2 mm | 3.39 | 1.380 | 1.107 | 1.588 | 1.347 | +2.4 % | pass | 1.716 |

#### Coil at 100 kHz (2 sin current sheets solved alone, time-harmonic)

Added resistance per phase is `-Im F` times `2*pi*f*L0`.

| Stack | PCB [mm] | model factor, DC | model Re F | FEMM Re F | error | | model -Im F | FEMM -Im F | error | |
|---|---|---|---|---|---|---|---|---|---|---|
| Al 3 mm @1 mm | 1.6 | 1.000 | 0.826 | 0.829 | -0.4 % | pass | 0.0292 | 0.0294 | -0.9 % | pass |
| Steel 1018 3 mm @1 mm | 1.6 | 1.208 | 1.166 | 1.169 | -0.3 % | pass | 0.0347 | 0.0350 | -0.8 % | pass |
| Si steel 0.35 mm | 1.6 | 1.592 | 1.562 | 1.565 | -0.2 % | pass | 0.0302 | 0.0304 | -0.7 % | pass |
| MnZn 2 mm + Al 3 mm @1 mm | 1.6 | 1.593 | 1.593 | 1.596 | -0.2 % | pass | 0.0000 | 0.0000 |  |  |
| Al 1 mm @0.3 mm (version 2 without the sheet) | 0.8 | 1.000 | 0.564 | 0.566 | -0.5 % | pass | 0.0734 | 0.0743 | -1.3 % | pass |
| Version 2 away from the magnets: flex 0.2 mm (mu 130) + Al 1 mm @0.1 mm | 0.8 | 1.624 | 1.619 | 1.625 | -0.4 % | pass | 0.0005 | 0.0005 |  |  |
| Version 2 under the magnets: flex 0.2 mm at the model's mu_inc 1.327 + Al | 0.8 | 1.019 | 0.595 | 0.598 | -0.5 % | pass | 0.0700 | 0.0702 | -0.3 % | pass |

#### Eddy drag of a travelling field (2-D fundamental, per B0^2/mu0 of the bare field at the stack top)

Normal forces below 0.005 are at FEMM's numerical floor (the no-stack rows above give ±0.002).

| Stack | v [m/s] | f [Hz] | model -Im R | FEMM drag | error | | model Re R | FEMM normal | error | | FEMM loss / (F v) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Al 3 mm @1 mm | 1 | 83 | 0.0050 | 0.0051 | -0.9 % | pass | -0.0001 | -0.0013 | floor |  | 1.002 |
| Al 3 mm @1 mm | 20 | 1667 | 0.0786 | 0.0796 | -1.2 % | pass | -0.0388 | -0.0402 | -3.6 % | pass | 1.000 |
| Al 3 mm @1 mm | 100 | 8333 | 0.1027 | 0.1046 | -1.9 % | pass | -0.1644 | -0.1675 | -1.9 % | pass | 1.000 |
| Steel 1018 3 mm @1 mm | 1 | 83 | 0.0020 | 0.0020 | -0.3 % | pass | +0.3488 | +0.3526 | -1.1 % | pass | 1.019 |
| Steel 1018 3 mm @1 mm | 20 | 1667 | 0.0090 | 0.0092 | -1.7 % | pass | +0.3416 | +0.3458 | -1.2 % | pass | 1.003 |
| Steel 1018 3 mm @1 mm | 100 | 8333 | 0.0195 | 0.0199 | -2.1 % | pass | +0.3302 | +0.3344 | -1.2 % | pass | 1.000 |
| Version 2: flex 0.2 mm at the model's mu_eff 2.07 + Al 1 mm @0.1 mm | 1 | 83 | 0.0068 | 0.0068 | -0.8 % | pass | +0.0729 | +0.0717 | +1.7 % | pass | 0.992 |
| Version 2: flex 0.2 mm at the model's mu_eff 2.07 + Al 1 mm @0.1 mm | 20 | 1667 | 0.1256 | 0.1258 | -0.2 % | pass | +0.0388 | +0.0377 | +2.7 % | pass | 1.000 |
| Version 2: flex 0.2 mm at the model's mu_eff 2.07 + Al 1 mm @0.1 mm | 100 | 8333 | 0.2392 | 0.2415 | -0.9 % | pass | -0.2418 | -0.2438 | -0.8 % | pass | 1.000 |

### Discussion

- **Thin saturated sheets pass** (flex 0.1, 0.2 and 1 mm): field ratio at
  the coil within 1.4 %, attraction +6 to +7 %, mean flux in the sheet +6 to
  +8 %, peak −5 to −8 %. The knee shape does not matter here: FEMM gives the
  same numbers with the tanh and with the two-slope curve. For version 2 FEMM
  confirms the collapse of the linear model: field ratio 1.051 instead of
  1.439, attraction 7.2 kPa instead of 91.3 kPa.
- **Thick plates near the knee fail.** 5 mm flex sheet (overload 1.00): field
  ratio +13 %, attraction +52 %, peak +34 %. 2 mm MnZn (overload 1.4):
  attraction +14 %, peak +15 %. 2.8 mm MnZn: attraction +7 % (pass), peak
  +16 %. FEMM's two-slope runs give the same field and force, so the cause is
  not the knee. Under the magnet centres the field enters the plate normally
  and saturates a skin at its face; the model only lets the in-plane field
  saturate a layer, so it keeps that skin permeable and overstates `R`. The
  peak column fails for the same reason. Modelling this needs an anisotropic
  (in-plane and normal) permeability per sublayer; it was not done. The
  thicknesses the warning suggests are therefore lower bounds, and the
  warning says "at least".
- **Incremental inductance passes** within 3 % of the mean over the two coil
  positions. FEMM spreads widely with position (1.004–1.060 for version 2,
  1.11–1.59 for 2 mm MnZn): the saturated sheet makes the inductance depend
  on where the mover is, which the model's single value does not show. An
  earlier version used the differential permeability only and gave 1.000,
  1.001 and 1.002 (−3 %, −11 %, −26 %).
- **Eddy currents pass everywhere.** Coil factor at 100 kHz within 0.5 %
  and added resistance within 1.3 %, including the 3 mm aluminium case
  (model 0.826×, FEMM 0.829×) that the static model put at 1.000×. Drag
  within 2.1 % and normal force within 3.6 % from 1 to 100 m/s, for
  aluminium, steel 1018 and the version 2 stack. FEMM's loss equals `F·v`
  within 2 %. The steel housing stays attractive at speed; the aluminium one
  repels.
- **Not checked.** The 3-D drag of the real 5 mm deep magnets: the model sums
  the cross-travel spectrum as for the attraction, which magpylib confirmed
  for the static case only. The array ends, which add entry and exit eddy
  currents in a real eddy brake. The weighting by magnet coverage. Hysteresis
  and core loss in the sheet, which moves through a saturated B-H loop at
  `v/(2τ)` and would add its own drag. Conductivity at operating temperature.

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
- Eddy currents are linear: the conductivity is constant and the ferrite and
  steel keep their μr for the AC field. Linear FEMM and the model keep 0.35 mm
  Si steel at about 1.56× at 100 kHz (1.59× static), because μr = 4000
  dominates the skin effect. Real lamination permeability and core loss at
  100 kHz are far worse, so the model's Si steel warning stays.
- Saturation from the normal field at the face of thick plates is missing,
  and the inductance under the magnets is one value where the real one
  depends on the mover position (see above).
- Hysteresis and core loss are not modelled, neither for the PWM ripple nor
  for the moving magnets.
- `attraction_n` is reported but does not yet load the bearing in the
  friction budget (`FrictionEstimator::from_config` uses zero normal force).
