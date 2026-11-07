import { describe, expect, it } from "vitest";
import { calculateDriver, emptyDriverInput, type DriverCalculatorSnapshot } from "./driverCalculator";
import { buildDriverExport, driverExportHtml } from "./driverCalculatorExport";

const input = () => ({ ...emptyDriverInput(), resistanceOhm: 2, inductanceH: 100e-6, seriesInductanceH: 50e-6, forceConstant: 1.5, currentA: 2, speedMS: .5, electricalPeriodM: .012 });

describe("driver calculator exports", () => {
  it("exports current inputs, driver limits and every screening result in SI units", () => {
    const values = input();
    const data = buildDriverExport(values, null, "2026-11-07T00:00:00Z");
    expect(data.result).toEqual(calculateDriver(values));
    expect(data.result.forceN).toBe(3);
    expect(data.result.phaseBackEmfV).toBe(.5);
    expect(data.result.lineBackEmfV).toBeCloseTo(Math.sqrt(3) * .5, 12);
    expect(data.result.effectiveH).toBeCloseTo(150e-6, 12);
    expect(data.input.resistanceOhm).toBe(2);
    expect(data.units.currentA).toContain("phase amplitude");
    expect(data.provenance.source).toBe("Manual inputs");
    expect(JSON.parse(JSON.stringify(data))).toEqual(data);
    values.driver.name = "Changed";
    expect(data.input.driver.name).not.toBe("Changed");
    const html = driverExportHtml(data);
    for (const text of ["Hot phase resistance", "External series inductance", "Ideal thrust", "Phase back-EMF", "Line-to-line back-EMF", "Model limits", "Maximum PWM", "Not evaluated"]) expect(html).toContain(text);
  });
  it("keeps optional quantities unknown, but evaluates zero-speed back-EMF", () => {
    const values = { ...input(), forceConstant: null, electricalPeriodM: null };
    const result = buildDriverExport(values, null).result;
    expect(result.forceN).toBeNull();
    expect(result.phaseBackEmfV).toBeNull();
    expect(result.lineBackEmfV).toBeNull();
    expect(result.speedV).toBeNull();
    expect(buildDriverExport({ ...values, speedMS: 0 }, null).result.phaseBackEmfV).toBe(0);
    expect(buildDriverExport({ ...input(), electricalPeriodM: null }, null).result.phaseBackEmfV).toBe(.5);
  });
  it("records edited imported provenance and escapes all user text in HTML", () => {
    const source: DriverCalculatorSnapshot = { source: '<script>alert("motor")</script>', capturedAt: "2026-11-07T00:00:00Z", native: false, input: input(), notes: ["Demo <estimate>"] };
    const data = buildDriverExport({ ...input(), resistanceOhm: 3, driver: { ...input().driver, name: '<img src=x onerror="alert(1)">' } }, source);
    expect(data.provenance.edited).toBe(true);
    expect(data.provenance.importedInput?.resistanceOhm).toBe(2);
    expect(buildDriverExport(source.input, source).provenance.edited).toBe(false);
    const html = driverExportHtml(data);
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("Browser demo estimates");
    expect(html).toContain("Edited in calculator");
  });
  it("exports validation errors without fabricating results for invalid or unsupported inputs", () => {
    for (const values of [emptyDriverInput(), { ...input(), connection: "delta" as const }, { ...input(), phaseCount: 4 }]) {
      const data = buildDriverExport(values, null);
      expect(data.result.errors.length).toBeGreaterThan(0);
      expect(data.result.checks).toEqual([]);
      expect(data.result.forceN).toBeUndefined();
      expect(driverExportHtml(data)).toContain("Not evaluated due to invalid or unsupported inputs");
    }
  });
});
