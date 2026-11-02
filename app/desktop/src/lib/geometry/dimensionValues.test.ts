import { describe, expect, it } from "vitest";
import { isPositiveFiniteDimension } from "./dimensionValues";

describe("positive finite dimension", () => {
  it("accepts positive finite numbers and rejects missing or invalid values", () => {
    for (const value of [Number.MIN_VALUE, 0.001, 1, Number.MAX_VALUE]) {
      expect(isPositiveFiniteDimension(value)).toBe(true);
    }
    for (const value of [null, undefined, -1, -0, 0, NaN, Infinity, -Infinity]) {
      expect(isPositiveFiniteDimension(value)).toBe(false);
    }
  });
});
