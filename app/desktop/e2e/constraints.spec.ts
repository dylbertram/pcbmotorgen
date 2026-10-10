import { test, expect } from "@playwright/test";
import {
  designConstraintsPanel,
  numberField,
  activeLengthReadout,
  traceTotalReadout,
  box,
  eventually,
  gotoDesignApp,
} from "./helpers";

test.describe("Design constraints restructure", () => {
  test("desired center-to-center travel is set in the Design constraints box", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    const travelInput = numberField(page, "Desired travel (center-to-center)");
    await expect(travelInput).toBeVisible();
    // It lives inside the Design constraints box (right column), not the left
    // reflection column.
    await expect(
      designConstraintsPanel(page).getByLabel("Desired travel (center-to-center)"),
    ).toBeVisible();

    // The old left-column "Driving parameters" box is gone.
    await expect(
      page.locator("section[aria-labelledby='driving-parameters-heading']"),
    ).toHaveCount(0);

    // Editing desired travel drives the active-area length output.
    const initialLength = (await activeLengthReadout(page).textContent())!.trim();
    await travelInput.fill("100");
    await eventually(async () => {
      await expect(activeLengthReadout(page)).toHaveText(/172\.0/);
    });
    // Active area length = coil span (72 mm default) + desired travel.
    expect(initialLength).not.toMatch(/172\.0/);

    // The PCB trace total (the traces' first-to-last X span, drawn by the
    // coil preview AND the design reflection) follows the travel edit. Since
    // kata hrd8 the routing domain EQUALS the active area — the braid's end
    // turns are part of the pattern and there is no 2 × 30 mm end padding
    // (the old "172 + 2 × 30 = 232.0" total was a pre-hrd8 expectation this
    // spec missed; padding is gone from the store, the IPC and the routing
    // crate) — so the mock braid measures 172.0 mm here. The "meas." suffix
    // pins the MEASURED payload, not the config fallback (which also reads
    // 172.0 right after the edit): it appears only once the debounced
    // generate → measure cycle lands a payload for the NEW travel.
    await eventually(async () => {
      await expect(traceTotalReadout(page)).toHaveText(/172\.0 mm meas\./);
    });
  }, { tag: ["@constraints", "@desktop"] });

  test("active area width, PCB thickness and air gap remain editable", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    // The four general geometry fields live inside the Design constraints box.
    await expect(page.locator("details", { hasText: "General" })).toHaveCount(0);

    const driver = designConstraintsPanel(page);
    await expect(driver).toBeVisible();
    await expect(numberField(page, "Active area width (mm)")).toBeVisible();
    await expect(numberField(page, "PCB thickness (mm)")).toBeVisible();
    await expect(numberField(page, "Air gap (mm)")).toBeVisible();
    await expect(driver.getByLabel("Active area width (mm)")).toBeVisible();
    await expect(driver.getByLabel("PCB thickness (mm)")).toBeVisible();
    await expect(driver.getByLabel("Air gap (mm)")).toBeVisible();

    // No active-area fields remain under the combined Topology & Board panel.
    const traces = page.locator(
      "section[aria-labelledby='topology-board-heading']",
    );
    await expect(traces).toBeVisible();
    expect(
      await traces.locator("input, select").evaluateAll(
        (els) => els.filter((el) => {
          const label = (el as HTMLInputElement).ariaLabel ?? "";
          return label.toLowerCase().includes("active area");
        }).length,
      ),
    ).toBe(0);

    // The old Stackup box is gone.
    await expect(
      page.locator("details", { hasText: "Stackup" }),
    ).toHaveCount(0);

    // The old driver toggle is gone and no range sliders remain in the
    // constraints box; the numeric fields are the editable controls. (The
    // mover-position slider in the design reflection aside is a separate
    // feature and is not counted here.)
    await expect(
      page.getByRole("button", { name: "Magnets", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Traces", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.locator(
        "section[aria-labelledby='design-constraints-heading'] input[type='range']",
      ),
    ).toHaveCount(0);

    await expect(numberField(page, "PCB thickness (mm)")).toBeEnabled();
    await expect(numberField(page, "Air gap (mm)")).toBeEnabled();
    await expect(numberField(page, "Active area width (mm)")).toBeEnabled();
  }, { tag: ["@constraints", "@desktop"] });

  test("routing source shares an unboxed heading row with its dropdown", async ({
    page,
  }) => {
    await gotoDesignApp(page);

    // No nested bordered section for routing parameters; they are part of the
    // combined Topology & Board panel.
    await expect(
      page.locator("section[aria-labelledby='routing-source-heading']"),
    ).toHaveCount(0);

    // The heading exists unboxed.
    const heading = page.locator("#routing-source-heading");
    await expect(heading).toBeVisible();

    // The pattern dropdown shares the title row: vertically centred against
    // the heading (same row, not a line above it), and it hangs LEFT —
    // starting immediately after the title.
    const select = page.locator("#routing-pattern");
    await expect(select).toBeVisible();
    const h = await box(page, heading);
    const s = await box(page, select);
    expect(h).not.toBeNull();
    expect(s).not.toBeNull();
    const hCenter = h!.y + h!.h / 2;
    const sCenter = s!.y + s!.h / 2;
    expect(Math.abs(sCenter - hCenter)).toBeLessThanOrEqual(2);
    expect(s!.x).toBeGreaterThanOrEqual(h!.x + h!.w - 2);
  }, { tag: ["@constraints", "@desktop"] });

  test("drive and force targets live in the Simulation tab", async ({ page }) => {
    await gotoDesignApp(page);

    await expect(
      page.locator("#panel-design").getByText("Drive & Force Targets", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.locator("#panel-simulate").getByText("Drive & Force Targets", { exact: true }),
    ).toHaveCount(1);

    await page.getByRole("tab", { name: /^Simulate/i }).click();
    await expect(
      page.locator("#panel-simulate").getByText("Drive & Force Targets", { exact: true }),
    ).toBeVisible();
  }, { tag: ["@constraints", "@desktop"] });
});
