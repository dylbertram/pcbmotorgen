import { describe, expect, it } from "vitest";
import { validateNumberDraft } from "./numberFieldValidation";

describe("numeric draft validation", () => {
  it("rejects blank and non-finite input", () => {
    expect(validateNumberDraft("  ", { integer: false }).error).toBe("Enter a number.");
    expect(validateNumberDraft("Infinity", { integer: false }).error).toBe("Enter a finite number.");
    expect(validateNumberDraft("not a number", { integer: false }).value).toBeNull();
  });

  it("checks integer, range and multiples in order", () => {
    const constraints = { integer: true, min: 2, max: 8, multipleOf: 2 };
    expect(validateNumberDraft("1.5", constraints).error).toBe("Value must be a whole number.");
    expect(validateNumberDraft("0", constraints).error).toBe("Value must be at least 2.");
    expect(validateNumberDraft("10", constraints).error).toBe("Value must be at most 8.");
    expect(validateNumberDraft("3", constraints).error).toBe("Value must be a multiple of 2.");
    expect(validateNumberDraft("8", constraints)).toEqual({ value: 8, error: null });
  });

  it("retains epsilon tolerance and ignores non-finite bounds", () => {
    expect(validateNumberDraft("4.0000000005", { integer: false, multipleOf: 2 }).error).toBeNull();
    expect(validateNumberDraft("-3.5", { integer: false, min: NaN, max: Infinity }))
      .toEqual({ value: -3.5, error: null });
  });
});
