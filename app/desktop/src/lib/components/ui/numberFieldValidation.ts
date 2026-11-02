import { isMultipleOf } from "./numberValidation";

interface NumberFieldConstraints {
  integer: boolean;
  min?: number;
  max?: number;
  multipleOf?: number;
}

export function validateNumberDraft(
  raw: string,
  { integer, min, max, multipleOf }: NumberFieldConstraints,
): { value: number | null; error: string | null } {
  if (raw.trim() === "") return { value: null, error: "Enter a number." };

  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return { value: null, error: "Enter a finite number." };
  if (integer && !Number.isInteger(parsed)) return { value: null, error: "Value must be a whole number." };
  if (min !== undefined && Number.isFinite(min) && parsed < min) {
    return { value: null, error: `Value must be at least ${min}.` };
  }
  if (max !== undefined && Number.isFinite(max) && parsed > max) {
    return { value: null, error: `Value must be at most ${max}.` };
  }
  if (multipleOf !== undefined && !isMultipleOf(parsed, multipleOf)) {
    return { value: null, error: `Value must be a multiple of ${multipleOf}.` };
  }
  return { value: parsed, error: null };
}
