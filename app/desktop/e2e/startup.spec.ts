import { expect, test } from "@playwright/test";

test.describe("startup chooser and new-design setup", () => {
  test("immediately shows recents and keeps Open project available when the list is empty", async ({ page }) => {
    await page.goto("/");
    const dialog = page.getByRole("dialog", { name: "Recent projects" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toBeFocused();
    await expect(dialog).toHaveCSS("outline-style", "none");
    await page.keyboard.press("Tab");
    const openProject = dialog.getByRole("button", { name: "Open project…" });
    await expect(openProject).toBeFocused();
    await expect(openProject).not.toHaveCSS("outline-style", "none");
    await expect(dialog.getByText("No recent projects yet.")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Open project…" })).toBeEnabled();
    await expect(dialog.getByRole("button", { name: "New design" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Import CAD" })).toBeVisible();
  });

  test("sets layer count and generated pattern before entering the app", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog");
    await startup.getByRole("button", { name: "New design" }).click();

    await expect(startup).toHaveAttribute("aria-labelledby", "startup-title");
    await expect(page.locator("#startup-pattern")).toBeVisible();
    await expect(page.locator("#startup-layers")).toHaveValue("4");
    await expect(page.locator("#startup-source")).toHaveCount(0);
    await expect(startup.getByRole("button", { name: "Import CAD", exact: true })).toHaveCount(1);

    await page.locator("#startup-layers").selectOption("6");
    await expect(page.locator("#startup-layers")).toHaveValue("6");
    await startup.getByRole("button", { name: "Create design" }).click();
    await expect(startup).toBeHidden();
    await expect(page.locator("#num-layers")).toContainText("6");
  });

  test("Import CAD uses a modal and the Design page has no inline import controls", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await startup.getByRole("button", { name: "Import CAD" }).click();
    const importDialog = page.getByRole("dialog", { name: "Import CAD" });
    await expect(importDialog).toBeVisible();
    await expect(importDialog.getByLabel("DXF units")).toBeVisible();
    await expect(importDialog.getByLabel("Z tolerance (mm)")).toBeVisible();
    await expect(importDialog.getByRole("button", { name: "About Z tolerance" })).toBeVisible();
    const traceWidth = importDialog.getByLabel("Trace width (mm)");
    await expect(traceWidth).toBeVisible();
    await expect(traceWidth).toHaveAttribute("type", "text");
    await traceWidth.fill("0.127");
    await traceWidth.evaluate((input: HTMLInputElement) => input.setSelectionRange(3, 3));
    await traceWidth.press("Backspace");
    await expect(traceWidth).toHaveValue("0.27");
    await expect(importDialog.getByLabel("Via drill (mm)")).toBeVisible();
    await expect(importDialog.getByLabel("Via annular ring (mm)")).toBeVisible();
    await expect(importDialog.locator("#cad-retry-layer-count")).toHaveCount(0);
    await expect(importDialog.getByRole("button", { name: "Choose DXF…" })).toBeVisible();

    await importDialog.getByRole("button", { name: "Cancel" }).click();
    await startup.getByRole("button", { name: "New design" }).click();
    await startup.getByRole("button", { name: "Create design" }).click();
    await expect(startup).toBeHidden();
    await expect(page.getByRole("button", { name: /Import DXF/i })).toHaveCount(0);
    await expect(page.getByLabel("DXF units")).toHaveCount(0);
  });
});
