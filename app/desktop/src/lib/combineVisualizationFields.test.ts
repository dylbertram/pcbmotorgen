import { expect, it } from "vitest";
import { combineVisualizationFields } from "./combineVisualizationFields";
import type { FieldPreview } from "./types/simulationVisualization";

it("adds native vectors, recomputes magnitude and preserves input samples", () => {
  const coil: FieldPreview = { method: "qualified-finite-copper-winding-xyz", scope: "test", magnets: [], samples: [{ position_m: [0, 0, 0], b_t: [1, 2, 0], magnitude_t: Math.sqrt(5) }] };
  const pm: FieldPreview = { ...structuredClone(coil), method: "analytical-pm-only-xyz", samples: [{ position_m: [0, 0, 0], b_t: [-1, 0, 3], magnitude_t: Math.sqrt(10) }] };
  const original = structuredClone({ coil, pm });
  const sum = combineVisualizationFields(coil, pm);
  expect(sum.samples[0].b_t).toEqual([0, 2, 3]); expect(sum.samples[0].magnitude_t).toBeCloseTo(Math.sqrt(13), 14);
  expect({ coil, pm }).toEqual(original);
  pm.samples[0].b_t = [-1, -2, 0]; expect(combineVisualizationFields(coil, pm).samples[0].magnitude_t).toBe(0);
  pm.samples[0].position_m[0] = .001; expect(() => combineVisualizationFields(coil, pm)).toThrow("grids differ");
  pm.samples = []; expect(() => combineVisualizationFields(coil, pm)).toThrow();
});
