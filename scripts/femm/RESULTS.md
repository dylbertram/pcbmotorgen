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
  (N·w·D). The model spreads `R·B0²/μ0` over the footprint N·τ·D, so its
  column is that pressure times τ/w. The last column is the same force
  measured on the magnets, as a numerical cross-check.
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

| Stack | model p [kPa] | FEMM p [kPa] | p error | model B ratio | FEMM B ratio | B error | FEMM p, magnet-side check [kPa] |
|---|---|---|---|---|---|---|---|
| No backplane | 0.0 | 0.0 |  | 1.000 | 1.000 | +0.0 % | -0.0 |
| FR4 1.6 mm | 0.0 | 0.0 |  | 1.000 | 0.999 | +0.1 % | -0.7 |
| MnZn 2 mm | 45.1 | 45.1 | +0 % | 1.218 | 1.220 | -0.1 % | 45.4 |
| MnZn 5 mm | 45.1 | 45.1 | -0 % | 1.218 | 1.221 | -0.2 % | 45.4 |
| Si steel 0.35 mm | 45.0 | 45.0 | +0 % | 1.218 | 1.220 | -0.1 % | 44.7 |
| Flex ferrite 0.3 mm | 37.1 | 37.1 | +0 % | 1.180 | 1.181 | -0.1 % | 37.2 |
| NiZn 2 mm | 44.9 | 44.9 | +0 % | 1.217 | 1.219 | -0.1 % | 45.2 |
| FR4 1 mm + MnZn 2 mm | 15.8 | 15.8 | +0 % | 1.077 | 1.076 | +0.1 % | 16.1 |
| MnZn 2 mm + Al 3 mm @1 mm | 45.1 | 45.0 | +0 % | 1.218 | 1.219 | -0.1 % | 45.4 |
| MnZn 2 mm + steel 3 mm @1 mm | 45.1 | 45.0 | +0 % | 1.218 | 1.219 | -0.1 % | 45.4 |
| Al 3 mm @1 mm (no layers) | 0.0 | -0.0 |  | 1.000 | 0.999 | +0.1 % | -0.5 |
| Steel 3 mm @1 mm (no layers) | 15.8 | 15.8 | +0 % | 1.076 | 1.077 | -0.0 % | 15.3 |

**Max attraction error: under 1 %. Max B-ratio error: −0.2 %.** At 5ffaafd
they were −85 % and −15 %. With no stack, the fundamental at the stack face is
0.2159 T in FEMM and `B0` = 0.2174 T in the model (+0.7 %). At 5ffaafd the
model used `field_at_gap`, 0.450 T.

## What changed since 5ffaafd

1. **Reflection.** `K = r·(1 − e^(−kT))` is replaced by the slab reflection
   `R = r(1 − e^(−2kT))/(1 − r²e^(−2kT))`. Magnetic layers are first collapsed
   into one slab with the series permeability. FR4 and the housing gap are
   air. In linear theory a 0.35 mm Si steel sheet reflects as fully as a thick
   block (R = 0.997). For thin sheets the linear value is an upper bound,
   because saturation is ignored. The model's estimate puts 0.35 mm Si steel
   (2.37 T) and 0.3 mm flex ferrite (2.52 T) above Bsat and warns.
2. **Attraction.** The pressure is `R·B0²/μ0`, the mean Maxwell stress on a
   reflecting face, over the footprint N·τ·D. `B0 = (2/π)·Br·sin(πw/2τ)·
   (1 − e^(−kh))·e^(−kd)` is the 2-D fundamental at the stack top.
3. **Housing.** The housing is folded into `R` with the layered-media
   recursion instead of adding a second image. 2 mm of MnZn screens it
   completely, as FEMM shows (1.596 with or without steel). An aluminium
   housing (μr = 1) changes nothing.
4. **Saturation.** The flux entering the stack top is `(1+R)·B0`.

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

## Remaining limits of `backplane/mod.rs`

- The inductance factor averages `N = num_layers` copper sheets spread
  evenly from the PCB bottom to the top, all with the same current (a
  series-connected coil). Real 4- and 6-layer stackups have uneven core and
  prepreg thicknesses, so the inner-layer depths are approximate. The average
  leaves out the coupling between layers. A pure-fundamental sheet set with
  that coupling gives 1.718× (2 sheets) against the model's 1.593×. The real
  winding has harmonics that weaken it, so it lands between the two
  (1.630×).
- Only the fundamental is modelled. The image magnets use the fundamental `R`
  for every harmonic, which is good for the field ratio here (−0.2 %).
- Eddy currents are not modelled. At the 100 kHz PWM, a 3 mm aluminium
  housing 1 mm below a bare PCB cuts inductance by 17 % (0.829×, sheets
  alone), and the model reports 1.000×. Behind 2 mm of MnZn the effect is gone.
  Linear FEMM keeps 0.35 mm Si steel at 1.565× at 100 kHz (1.592× static), because μr = 4000 dominates the
  skin effect. Real lamination permeability and loss at 100 kHz are far worse
  than this linear run, so the model's Si steel warning stays.
- Saturation is outside this check. Every FEMM run is linear, so the thin-sheet
  rows (Si steel, flex ferrite) are upper bounds. The next step is a nonlinear
  FEMM run with the magnets present and a B-H curve, using FEMM's
  incremental-permeability solve for the coil inductance.
