/**
 * Magnet grade reference catalog (NdFeB) and grade → remanence helpers.
 *
 * Source values live in PRODUCT_GOALS.md §3.C.
 */

export interface MagnetGrade {
  name: string;
  br_min_t: number;
  br_typ_t: number;
  br_max_t: number;
  max_temp_c: Record<string, number>;
}

export const CUSTOM_GRADE = "Custom";

export const MAGNET_GRADES: Record<string, MagnetGrade> = {
  N35: { name: "N35", br_min_t: 1.17, br_typ_t: 1.19, br_max_t: 1.21, max_temp_c: { Std: 80, H: 120, SH: 150, UH: 180, EH: 200, AH: 220 } },
  N38: { name: "N38", br_min_t: 1.21, br_typ_t: 1.23, br_max_t: 1.25, max_temp_c: { Std: 80, H: 120, SH: 150, UH: 180, EH: 200, AH: 220 } },
  N42: { name: "N42", br_min_t: 1.28, br_typ_t: 1.30, br_max_t: 1.32, max_temp_c: { Std: 80, H: 120, SH: 150, UH: 180, EH: 200, AH: 220 } },
  N44: { name: "N44", br_min_t: 1.32, br_typ_t: 1.34, br_max_t: 1.36, max_temp_c: { Std: 80, H: 120, SH: 150, UH: 180, EH: 200, AH: 220 } },
  N48: { name: "N48", br_min_t: 1.38, br_typ_t: 1.40, br_max_t: 1.42, max_temp_c: { Std: 80, H: 120, SH: 150, UH: 180, EH: 200, AH: 220 } },
  N52: { name: "N52", br_min_t: 1.43, br_typ_t: 1.45, br_max_t: 1.48, max_temp_c: { Std: 80 } },
};

/** Extract base grade (e.g. "N44H" → "N44"). */
export function extractBaseGrade(grade: string): string {
  const m = grade.trim().match(/^([Nn]\d+)/);
  return m ? m[1].toUpperCase() : grade.trim();
}

/** Typical Br [T] for a grade name (handles thermal suffixes). */
export function getRemanence(grade: string): number {
  const base = extractBaseGrade(grade);
  return MAGNET_GRADES[base].br_typ_t;
}
