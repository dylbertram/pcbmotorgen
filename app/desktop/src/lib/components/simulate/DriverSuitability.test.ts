import { describe, expect, it } from "vitest";
import { render } from "svelte/server";
import { mockDriveAnalysis } from "../../ipc/mocks";
import { ConfigStore } from "../../stores/config.svelte";
import DriverSuitability from "./DriverSuitability.svelte";

// Presentation fixtures only, not numerical driver or force qualification.
function analysis() {
  const config = new ConfigStore();
  return mockDriveAnalysis(config.toIpc(), config.drive, null);
}

describe("driver suitability result states", () => {
  it("renders a pending state without dereferencing absent analysis", () => {
    const { body } = render(DriverSuitability, { props: { analysis: null } });
    expect(body).toContain("Measuring the routed copper");
    expect(body).not.toContain('aria-label="Voltage and speed"');
    expect(body).not.toContain('role="alert"');
  });

  it("renders an error without pending or stale result sections", () => {
    const { body } = render(DriverSuitability, {
      props: { analysis: null, error: "Driver unavailable" },
    });
    expect(body).toContain("Driver analysis failed: Driver unavailable");
    expect(body).toContain('role="alert"');
    expect(body).not.toContain("Measuring the routed copper");
    expect(body).not.toContain('aria-label="Operating limits"');
  });

  it("does not show a warning/failure meter for passing checks", () => {
    const value = analysis();
    value.checks = [{ ...value.checks[0], status: "pass" }];
    const { body } = render(DriverSuitability, { props: { analysis: value } });
    expect(body).toContain('aria-label="Voltage and speed"');
    expect(body).not.toContain("check-meter");
  });

  it.each(["warn", "fail"] as const)("renders a %s meter for its narrowed check status", (status) => {
    const value = analysis();
    value.checks = [{ ...value.checks[0], status }];
    const { body } = render(DriverSuitability, { props: { analysis: value } });
    expect(body).toContain("check-meter");
    expect(body).toContain(`h-1 rounded-full ${status === "warn" ? "bg-amber-400" : "bg-rose-400"}`);
  });
});
