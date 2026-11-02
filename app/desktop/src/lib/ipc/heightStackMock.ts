import type { HeightStackResultDto, LinearMotorConfig } from "../types";

/** Copper protrusion per side above the substrate (m) — 1oz ≈ 35 µm. */
const COPPER_PROTRUSION_1OZ_M = 35e-6;
/** Solder-mask coating thickness (m). */
const SOLDER_MASK_M = 20e-6;
/** Assembly tolerance allowance in the height stack (m). */
const TOLERANCE_M = 0.1e-3;

/** Browser-only height stack. It does not calculate backplane analysis. */
export function mockHeightStack(c: LinearMotorConfig): HeightStackResultDto {
  const backplane_m = c.backplane?.layers.reduce((sum, l) => sum + l.thickness_m, 0) ?? 0;
  const housing_gap_m = c.backplane?.housing?.gap_m ?? 0;
  const housing_m = c.backplane?.housing?.thickness_m ?? 0;
  const cu_protrusion_m = c.pcb_stackup ? 0 : COPPER_PROTRUSION_1OZ_M * (c.num_layers >= 6 ? 2 : 1);
  return {
    pcb_thickness_m: c.pcb_thickness_m,
    cu_protrusion_m,
    solder_mask_m: SOLDER_MASK_M,
    air_gap_m: c.air_gap_m,
    magnet_height_m: c.magnet_height_m,
    tolerance_m: TOLERANCE_M,
    backplane_m,
    housing_gap_m,
    housing_m,
    total_height_m:
      c.pcb_thickness_m + cu_protrusion_m + SOLDER_MASK_M + c.air_gap_m + c.magnet_height_m + TOLERANCE_M +
      backplane_m + housing_gap_m + housing_m,
    backplane_analysis: null,
  };
}
