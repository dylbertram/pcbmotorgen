import { describe, expect, it } from "vitest";
import { isMultipleOf } from "./numberValidation";

describe("isMultipleOf", () => {
  it("accepts whole multiples", () => {
    expect(isMultipleOf(4, 2)).toBe(true);
    expect(isMultipleOf(2, 2)).toBe(true);
    expect(isMultipleOf(2.5, 0.5)).toBe(true);
  });

  it("rejects non-multiples", () => {
    expect(isMultipleOf(3, 2)).toBe(false);
    expect(isMultipleOf(1.3, 0.5)).toBe(false);
  });

  it("is epsilon-tolerant like the routing crate (1e-9)", () => {
    expect(isMultipleOf(4 + 5e-10, 2)).toBe(true);
    expect(isMultipleOf(4 + 1e-6, 2)).toBe(false);
  });

  it("passes degenerate inputs through (backend owns rejection)", () => {
    expect(isMultipleOf(Number.NaN, 2)).toBe(true);
    expect(isMultipleOf(4, 0)).toBe(true);
    expect(isMultipleOf(4, Number.NaN)).toBe(true);
  });
});
