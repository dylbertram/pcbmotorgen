import { expect, it } from "vitest";
import { copperLayerPositionsMm } from "./copperLayerPlacement";

it("scales source ratios to configured thickness, with the top at zero", () => {
  const raw = [-4.8, -3.2, -1.6, 0];
  const placed = copperLayerPositionsMm(raw, 1.6);
  [-1.6, -1.0666666666666667, -.5333333333333333, 0].forEach((v, i) => expect(placed[i]).toBeCloseTo(v, 12));
  expect(raw).toEqual([-4.8, -3.2, -1.6, 0]);
  expect(copperLayerPositionsMm([8, 7, 4], 1.6)).toEqual([0, -.4, -1.6]);
  expect(copperLayerPositionsMm([5], 1.6)).toEqual([0]);
  copperLayerPositionsMm(raw, 3.2).forEach((v, i) => expect(v).toBeCloseTo(2 * placed[i], 12));
});

it("rejects invalid placement rather than flattening multiple layers", () => {
  for (const raw of [[], [0, 0], [NaN, 0], [-Infinity, 0]]) expect(() => copperLayerPositionsMm(raw, 1.6)).toThrow();
  expect(() => copperLayerPositionsMm([-1, 0], 0)).toThrow();
});
