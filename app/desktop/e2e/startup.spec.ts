import { expect, test } from "@playwright/test";

test.describe("startup chooser and new-design setup", () => {
  test("immediately shows recents and keeps Open project available when the list is empty", async ({ page }) => {
    await page.goto("/");
    const dialog = page.getByRole("dialog", { name: "Recent projects" });
    await expect(dialog).toBeVisible();
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
    await expect(page.locator("#startup-source")).toHaveCount(0);
    await expect(startup.getByRole("button", { name: "Import CAD", exact: true })).toHaveCount(1);

    await page.locator("#startup-layers").selectOption("6");
    await startup.getByRole("button", { name: "Create design" }).click();
    await expect(startup).toBeHidden();
    await expect(page.locator("#num-layers")).toContainText("6");
  });

  test("Import CAD opens a single dedicated import setup", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await startup.getByRole("button", { name: "Import CAD" }).click();
    await expect(startup.getByRole("heading", { name: "Import CAD" })).toBeVisible();
    await expect(page.locator("#import-layer-count")).toBeVisible();
    await expect(startup.getByRole("button", { name: "Import DXF…" })).toBeVisible();
    await expect(startup.getByText(/centerlines/i)).toHaveCount(0);
  });
});
