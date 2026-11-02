import { expect, it } from "vitest";
import { stripBoundsDomainMm } from "./moverBounds";

it("centers the mover span on the clamped routing-frame position", () => {
  expect(stripBoundsDomainMm({ mover_span_mm: 7 }, { clampedPositionMm: 2 }))
    .toEqual({ startMm: -1.5, endMm: 5.5 });
  expect(stripBoundsDomainMm({ mover_span_mm: 0 }, { clampedPositionMm: 12 }))
    .toEqual({ startMm: 12, endMm: 12 });
});
