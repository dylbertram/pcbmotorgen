import { expect, test } from "@playwright/test";

test.describe("startup chooser and new-design setup", () => {
  test("offers import, recent, and new design flows", async ({ page }) => {
    await page.goto("/");
    const dialog = page.getByRole("dialog", { name: "Start a design" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Import CAD" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Load Recent" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "New Design" })).toBeVisible();

    await dialog.getByRole("button", { name: "Load Recent" }).click();
    await expect(page.getByRole("dialog", { name: "Open a recent design" })).toBeVisible();
    await expect(page.getByText("No recent project files yet.")).toBeVisible();
  });

  test("sets millimetres, layer count, and generated pattern before entering the app", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog");
    await startup.getByRole("button", { name: "New Design" }).click();

    await expect(startup).toHaveAttribute("aria-labelledby", "startup-title");
    await expect(page.locator("#startup-units")).toHaveValue("Millimetres (mm)");
    await expect(page.locator("#startup-pattern")).toBeVisible();
    await expect(page.locator("input[name='startup-source'][value='generated']")).toBeChecked();

    await page.locator("#startup-layers").selectOption("6");
    await startup.getByRole("button", { name: "Create design" }).click();
    await expect(startup).toBeHidden();
    await expect(page.locator("#num-layers")).toContainText("6");
  });

  test("import flow still collects stack settings and keeps units fixed to mm", async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Start a design" });
    await startup.getByRole("button", { name: "Import CAD" }).click();
    await expect(page.locator("#startup-units")).toHaveValue("Millimetres (mm)");
    await expect(page.locator("input[name='startup-source'][value='import']")).toBeChecked();
    await expect(page.getByRole("button", { name: "Choose DXF…" })).toBeVisible();
  });
});
