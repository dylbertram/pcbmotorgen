import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

for (const mobile of [false, true]) {
  test(`rail panels select their required workflow and viewport ${mobile ? "mobile" : "desktop"}`, async ({ page }, info) => {
    if (mobile) await page.setViewportSize({ width: 390, height: 844 });
    await gotoDesignApp(page);
    const fields = page.getByRole("toolbar", { name: "Preview side tools", exact: true }).getByRole("button", { name: "Field and loss settings", exact: true });
    const panel = page.getByRole("dialog", { name: "Field and loss settings", exact: true });
    await expect(page.getByRole("tab", { name: /^Design/i })).toHaveAttribute("aria-selected", "true");
    await fields.click();
    await expect(page.getByRole("tab", { name: /^Simulate/i })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("button", { name: "3D fields and heat", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(panel).toBeVisible();
    await expect(page.getByTestId("coil-iso").getByRole("group", { name: "3D simulation overlays", exact: true })).toHaveCount(0);
    await panel.getByRole("combobox", { name: "Magnetic field source", exact: true }).selectOption("pm");
    await panel.getByRole("combobox", { name: "Field sample density", exact: true }).selectOption("dense");
    await panel.getByRole("slider", { name: "Field overlay opacity", exact: true }).fill("0.3");
    await panel.getByRole("button", { name: "Close field and loss settings panel", exact: true }).click();
    await expect(fields).toBeFocused();
    await expect(panel).toBeHidden();
    await fields.click();
    await expect(panel.getByRole("combobox", { name: "Magnetic field source", exact: true })).toHaveValue("pm");
    await expect(panel.getByRole("combobox", { name: "Field sample density", exact: true })).toHaveValue("dense");
    await expect(panel.getByRole("slider", { name: "Field overlay opacity", exact: true })).toHaveValue("0.3");
    await page.screenshot({ path: info.outputPath("right-rail-field-settings.png") });
    await page.getByRole("tab", { name: /^Design/i }).click();
    await expect(panel).toBeHidden();
    await expect(fields).toHaveAttribute("aria-expanded", "false");

    const ends = page.getByRole("button", { name: "Set coil terminals", exact: true });
    for (const [label, id] of [["Front", "front"], ["Left", "left"], ["3D fields and heat", "iso"]]) {
      await page.getByRole("button", { name: label, exact: true }).click();
      await expect(page.getByTestId(`coil-${id}`)).toBeVisible();
      await expect(ends).toBeEnabled();
      await ends.click();
      await expect(page.getByRole("button", { name: "Top-down", exact: true })).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByRole("dialog", { name: "Coil terminals", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Close terminals panel", exact: true }).click();
    }
    // A compatible spatial view is preserved; only the workflow needs changing.
    await page.getByRole("button", { name: "Front", exact: true }).click();
    await fields.click();
    await expect(page.getByRole("tab", { name: /^Simulate/i })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("button", { name: "Front", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(panel).toBeVisible();
    await ends.click();
    await expect(panel).toBeHidden();
    await expect(page.getByRole("button", { name: "Top-down", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("tab", { name: /^Simulate/i })).toHaveAttribute("aria-selected", "true");
  });
}
