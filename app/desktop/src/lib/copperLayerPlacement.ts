import type { CadGeometry } from "./types";
import { pcbStackupHeightsMm, validatePcbStackup, type PcbStackupMm } from "./pcbStackup";

/** Raw CAD Z encodes relative spacing, not the physical PCB thickness. */
export function copperLayerPositionsMm(raw: number[], pcbThicknessMm: number, stackup?: PcbStackupMm | null): number[] {
  if (stackup) {
    validatePcbStackup(stackup, raw.length, pcbThicknessMm);
    return pcbStackupHeightsMm(stackup);
  }
  if (!raw.length || raw.some(z => !Number.isFinite(z)) || !Number.isFinite(pcbThicknessMm) || pcbThicknessMm <= 0)
    throw new Error("Finite layer heights and a positive PCB thickness are required.");
  const low = Math.min(...raw), high = Math.max(...raw);
  if (raw.length > 1 && (!(high > low) || !Number.isFinite(high - low)))
    throw new Error("Distinct finite layer heights are required for proportional PCB placement.");
  return raw.map(z => high === low ? 0 : (z - high) / (high - low) * pcbThicknessMm);
}

export function placedCopperGeometry(geometry: CadGeometry, pcbThicknessMm: number, stackup?: PcbStackupMm | null): CadGeometry {
  return { ...geometry, layer_z_mm: copperLayerPositionsMm(geometry.layer_z_mm, pcbThicknessMm, stackup) };
}
