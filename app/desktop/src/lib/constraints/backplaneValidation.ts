import { BACKPLANE_MAX_LAYERS, BACKPLANE_MAX_THICKNESS_M, HOUSING_MAX_THICKNESS_M, HOUSING_MAX_GAP_M, BACKPLANE_MAX_MU_R, BACKPLANE_MAX_BSAT_T, isSupportedHousingMaterial, type BackplaneStack } from "../types/backplane";
import type { Finding } from "./validation";

/** Explain unsupported restored settings without clamping or rewriting them. */
export function validateBackplaneInput(stack: BackplaneStack | null | undefined): Finding[] {
  if (!stack) return [];
  const findings: Finding[] = [];
  if (stack.layers.length > BACKPLANE_MAX_LAYERS) findings.push({ id: "backplane-layer-limit", level: "error", message: `Backplane supports at most ${BACKPLANE_MAX_LAYERS} layers; saved layers have not been removed.` });
  stack.layers.forEach((layer, index) => {
    if (!Number.isFinite(layer.thickness_m) || layer.thickness_m <= 0 || layer.thickness_m > BACKPLANE_MAX_THICKNESS_M) {
      findings.push({ id: `backplane-${index}-thickness`, level: "error", message: `Layer ${index + 1} thickness must be greater than 0 and at most 2 mm.` });
    }
    if (layer.mu_r != null && (!Number.isFinite(layer.mu_r) || layer.mu_r < 1 || layer.mu_r > BACKPLANE_MAX_MU_R)) findings.push({ id: `backplane-${index}-mu`, level: "error", message: `Layer ${index + 1} has an unsupported relative permeability.` });
    if (layer.bsat_t != null && (!Number.isFinite(layer.bsat_t) || layer.bsat_t <= 0 || layer.bsat_t > BACKPLANE_MAX_BSAT_T)) findings.push({ id: `backplane-${index}-bsat`, level: "error", message: `Layer ${index + 1} has an unsupported saturation flux density.` });
  });
  const housing = stack.housing;
  if (housing) {
    if (!isSupportedHousingMaterial(housing.material)) findings.push({ id: "housing-material", level: "error", message: "Housing must use aluminum or non-magnetic stainless 304/316. The saved material has not been changed." });
    if (!Number.isFinite(housing.thickness_m) || housing.thickness_m <= 0 || housing.thickness_m > HOUSING_MAX_THICKNESS_M) findings.push({ id: "housing-thickness", level: "error", message: "Housing wall thickness must be greater than 0 and at most 5 mm." });
    if (!Number.isFinite(housing.gap_m) || housing.gap_m < 0 || housing.gap_m > HOUSING_MAX_GAP_M) findings.push({ id: "housing-gap", level: "error", message: "Housing gap must be between 0 and 10 mm." });
  }
  return findings;
}
