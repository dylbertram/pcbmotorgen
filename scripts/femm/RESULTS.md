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
- **Inductance factor**: a sinusoidal current sheet (48 strips) at the PCB
  midplane, which is the model's own assumption. Factor =
  ∫A·J with the stack / ∫A·J without it. "Exact 1-D" is the closed-form
  slab solution `1 + R·e^(−2k·d)`, with `R = r(1−e^(−2kT))/(1−r²e^(−2kT))` and
  `r = (μ−1)/(μ+1)`.
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
- **Mesh check**: halving every mesh size moves the MnZn 2 mm sheet factor
  from 1.437 to 1.435, the benchmark-slice factor from 1.630 to 1.626, and the
  pressure from 45.1 to 45.1 kPa. The FR4 and no-stack rows give 1.000 ± 0.002,
  which is the numerical floor. FEMM matches the exact 1-D solution within 0.4 %
  on every single-slab row.

## Inductance factor (sin current sheet at the PCB midplane)

The model error is (model − FEMM) / FEMM. "model K" is the composite
reflection `R` at the PCB bottom, housing included.

| Stack | model K | model factor | FEMM factor | exact 1-D | model error | FEMM 100 kHz |
|---|---|---|---|---|---|---|
| No backplane | 0.000 | 1.000 | 1.000 |  | +0.0 % | 1.000 |
| FR4 1.6 mm | 0.000 | 1.000 | 1.001 | 1.000 | -0.1 % |  |
| MnZn 2 mm | 0.999 | 1.432 | 1.437 | 1.432 | -0.3 % |  |
| MnZn 5 mm | 0.999 | 1.432 | 1.437 | 1.432 | -0.3 % |  |
| Si steel 0.35 mm | 0.997 | 1.431 | 1.436 | 1.431 | -0.3 % | 1.414 |
| Flex ferrite 0.3 mm | 0.823 | 1.356 | 1.360 | 1.356 | -0.3 % |  |
| NiZn 2 mm | 0.995 | 1.430 | 1.435 | 1.430 | -0.3 % |  |
| FR4 1 mm + MnZn 2 mm | 0.351 | 1.152 | 1.154 |  | -0.2 % |  |
| MnZn 2 mm + Al 3 mm @1 mm | 0.999 | 1.432 | 1.437 |  | -0.3 % | 1.437 |
| MnZn 2 mm + steel 3 mm @1 mm | 0.999 | 1.432 | 1.437 |  | -0.3 % | 1.437 |
| Al 3 mm @1 mm (no layers) | 0.000 | 1.000 | 1.002 |  | -0.2 % | 0.875 |
| Steel 3 mm @1 mm (no layers) | 0.350 | 1.151 | 1.154 |  | -0.2 % | 1.124 |

**Max model error: −0.3 %.** At 5ffaafd it was −25.3 % (0.35 mm Si steel).
Halving the mesh moves the MnZn sheet factor by only 0.14 % (1.437 → 1.435), so
mesh size explains at most a small part of the remaining −0.3 %. The rest is
unexplained. The 48-strip sheet discretisation and the far-boundary approximation
are candidates that have not been tested.

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
   completely, as FEMM shows (1.432 with or without steel). An aluminium
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

| Slice | FEMM L-L factor | FEMM phase-A factor |
|---|---|---|
| MnZn 2 mm, L1 copper on the ferrite | 1.630 | 1.675 |
| MnZn 2 mm under a 0.1 mm mask/adhesive gap | 1.511 | 1.579 |
| MnZn 5 mm | 1.631 | 1.676 |
| mu_r 1e5, 20 mm (one-sided limit) | 1.631 | 1.676 |
| MnZn 2 mm + steel yoke on the magnet backs (y = 5.1 mm) | 1.653 | 1.707 |
| MnZn 2 mm + mu_r 1e5 yoke 1.0 mm above the PCB | 1.969 | 2.133 |
| MnZn 2 mm + mu_r 1e5 yoke 0.5 mm above the PCB | 2.255 | 2.494 |
| MnZn 2 mm + mu_r 1e5 yoke 0.3 mm above the PCB | 2.446 | 2.723 |

- **Neither 1.27× nor 2.4× is right.** FEMM gives **1.63×** line-to-line on
  2 mm MnZn when the bottom copper sits on the ferrite, and 1.51× with a 0.1 mm
  mask or adhesive gap. A thicker plate or ideal iron gives the same 1.63×.
  The model gives 1.43× (2 mm MnZn) and 1.39× (0.1 mm FR4 + 2 mm MnZn) for a
  sheet at the PCB midplane, from `backplane_dump`. Both fall in the requested
  1.27–1.48× range. Against the DXF slice in FEMM they are low (−12 % and −8 %),
  because the model puts all copper at the midplane while the bottom layer lies
  on the ferrite.
- The model gives 1.43× for 5 mm at τ = 6 mm, the same as for 2 mm.
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

- The inductance factor puts the copper at the PCB midplane. For a 2-layer
  board with the bottom layer on the backplane, FEMM gives 1.63× against the
  model's 1.43×.
- Only the fundamental is modelled. The image magnets use the fundamental `R`
  for every harmonic, which is good for the field ratio here (−0.2 %).
- Eddy currents are not modelled. At the 100 kHz PWM, a 3 mm aluminium
  housing 1 mm below a bare PCB cuts inductance by 12.5 % (0.875×), and the
  model reports 1.000×. Behind 2 mm of MnZn the effect is gone. Linear FEMM
  keeps 0.35 mm Si steel at 1.41× at 100 kHz, because μr = 4000 dominates the
  skin effect. Real lamination permeability and loss at 100 kHz are far worse
  than this linear run, so the model's Si steel warning stays.
- Saturation is outside this check. Every FEMM run is linear, so the thin-sheet
  rows (Si steel, flex ferrite) are upper bounds. The next step is a nonlinear
  FEMM run with the magnets present and a B-H curve, using FEMM's
  incremental-permeability solve for the coil inductance.
