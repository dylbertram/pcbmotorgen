import { describe, expect, it } from "vitest";
import { render } from "svelte/server";
import type { DriveAnalysis, PhaseElectrical } from "../../types";
import CurrentBudget from "./CurrentBudget.svelte";
import MetricsPanel from "./MetricsPanel.svelte";
import type { ConfigStore } from "../../stores/config.svelte";

// Only the fields read by the current budget are needed in these render tests.
function analysis(overrides: Partial<DriveAnalysis> = {}): DriveAnalysis {
  return {
    phase_current_a: 1,
    peak_current_a: 1.25,
    ripple_pp_a: 0.5,
    bus_voltage_v: 12,
    max_continuous_current_a: 2,
    limiting_factor: "trace ampacity",
    phases: ["A", "B", "C"].map((net) => ({ net, connected: true }) as PhaseElectrical),
    ...overrides,
  } as DriveAnalysis;
}

describe("CurrentBudget", () => {
  it("distinguishes selected current from the peak estimate on each terminal", () => {
    const { body } = render(CurrentBudget, { props: { analysis: analysis() } });
    expect(body).toContain("Selected phase current, before PWM ripple");
    expect(body).toContain("1.00 A");
    for (const net of ["A", "B", "C"]) {
      expect(body).toContain(`${net} terminal peak, including PWM ripple`);
    }
    expect(body.match(/1\.25 A/g)).toHaveLength(3);
    expect(body).toContain("0.50 A");
  });

  it("does not present phase current as a calculated DC supply requirement", () => {
    const { body } = render(CurrentBudget, { props: { analysis: analysis() } });
    expect(body).toContain("DC supply peak at 12.0 V");
    expect(body).toContain("Not calculated");
    expect(body).toContain("do not multiply the phase current by the bus voltage");
    expect(body).toContain("These estimates do not mean the driver checks pass");
  });

  it("does not show a predicted terminal current for an open circuit", () => {
    const { body } = render(CurrentBudget, {
      props: { analysis: analysis({ phases: [{ net: "U", connected: false } as PhaseElectrical] }) },
    });
    expect(body).toContain("U terminal peak");
    expect(body).toContain("Open circuit");
    expect(body).not.toContain("1.25 A");
  });

  it("handles unbounded ripple estimates without displaying Infinity or NaN", () => {
    const { body } = render(CurrentBudget, {
      props: { analysis: analysis({ peak_current_a: Infinity, ripple_pp_a: NaN }) },
    });
    expect(body).toContain("Not available");
    expect(body).not.toMatch(/Infinity|NaN/);
  });

  it("shows the selected input, terminal peaks and calculated ceiling in the metrics summary", () => {
    const { body } = render(MetricsPanel, {
      props: {
        config: { commutation: "max_thrust", phases: 3, max_current_a: 1, supply_voltage_v: 12 } as ConfigStore,
        sweep: null,
        friction: null,
        height: null,
        drive: analysis(),
      },
    });
    expect(body).toContain("Selected simulation inputs");
    expect(body).toContain("1.00 A phase amplitude");
    expect(body).toContain("1.25 A");
    expect(body).toContain("Calculated continuous phase-current ceiling");
    expect(body).toContain("2.00 A");
    expect(body).toContain("trace ampacity");
    expect(body).toContain("Not calculated");
  });
});
