import { describe, expect, it } from "vitest";
import { AnalysisWorkspace } from "./analysisWorkspace.svelte";

describe("analysis editor group", () => {
  it("opens once, closes independently, and keeps its split width", () => {
    const group = new AnalysisWorkspace();
    expect(group.driverCheckOpen).toBe(false);
    group.openDriverCheck();
    group.resize(62);
    group.openDriverCheck();
    expect(group.driverCheckOpen).toBe(true);
    expect(group.focusedGroup).toBe("driver");
    group.closeDriverCheck();
    expect(group.focusedGroup).toBe("design");
    group.openDriverCheck();
    expect(group.leftPercent).toBe(62);
  });

  it("is independent per source document and bounds resize inputs", () => {
    const a = new AnalysisWorkspace(), b = new AnalysisWorkspace();
    a.openDriverCheck();
    a.simulationView = "advanced";
    expect(b.driverCheckOpen).toBe(false);
    expect(b.simulationView).toBe("move");
    a.resize(200);
    expect(a.leftPercent).toBe(75);
    a.resize(-1);
    expect(a.leftPercent).toBe(30);
    a.resize(NaN);
    expect(a.leftPercent).toBe(30);
  });
});
