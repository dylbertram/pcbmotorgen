import { describe, expect, it } from "vitest";
import { AnalysisWorkspace } from "./analysisWorkspace.svelte";

describe("simulation view selection", () => {
  it("belongs to each editor view", () => {
    const left = new AnalysisWorkspace(), right = new AnalysisWorkspace();
    left.simulationView = "force";
    expect(right.simulationView).toBe("move");
  });
});
