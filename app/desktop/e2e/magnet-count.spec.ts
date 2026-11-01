import { expect, test } from "@playwright/test";
import { gotoDesignApp, selectDesignPanel } from "./helpers";

test("electrical pitch commits below the magnet limit and reports an oversized magnet", async ({ page }) => {
  await gotoDesignApp(page);
  await selectDesignPanel(page, "Magnets");
  const width = page.locator("#magnet-width");
  await expect(width).toHaveAttribute("max", "6");
  await width.fill("5"); await width.press("Tab");
  await selectDesignPanel(page, "Routing");
  const pitch = page.locator("#electrical-pitch");
  await expect(pitch).toHaveAttribute("min", "0.1");
  await expect(pitch).toHaveAttribute("max", "40");
  await pitch.fill("9");
  await pitch.press("Tab");
  await expect(pitch).toHaveValue("9");
  await expect(pitch).toHaveAttribute("aria-invalid", "false");
  const oversized = page.getByRole("alert").filter({ hasText: "Magnet X length (5.00 mm) is too big for the 4.50 mm pole pitch" });
  await expect(oversized).toBeVisible();
  await expect(oversized).toContainText("increase electrical pitch to 10.00 mm or more");
  await selectDesignPanel(page, "Magnets");
  await expect(width).toHaveValue("5");
  await expect(width).toHaveAttribute("max", "4.5");
  await selectDesignPanel(page, "Routing");
  await expect(pitch).toHaveValue("9");
  await expect(oversized).toBeVisible();
  await pitch.fill("10"); await pitch.press("Tab");
  await expect(pitch).toHaveValue("10");
  await expect(oversized).toHaveCount(0);
  await selectDesignPanel(page, "Magnets");
  await expect(width).toHaveValue("5");
  await expect(width).toHaveAttribute("max", "5");
  await width.fill("5.1"); await expect(width).toHaveAttribute("aria-invalid", "true");
  await width.press("Tab"); await expect(width).toHaveValue("5");
});

test("a small pitch can be corrected by reducing magnet size without changing the pitch", async ({ page }) => {
  await gotoDesignApp(page);
  await selectDesignPanel(page, "Routing");
  const pitch = page.locator("#electrical-pitch");
  await pitch.fill("2"); await pitch.press("Tab");
  await expect(pitch).toHaveValue("2");
  await expect(page.getByRole("alert").filter({ hasText: "is too big for the 1.00 mm pole pitch" })).toBeVisible();
  await selectDesignPanel(page, "Magnets");
  await expect(page.locator("#magnet-width")).toHaveValue("4.5");
  await page.locator("#magnet-width").fill("0.75");
  await page.locator("#magnet-width").press("Tab");
  await selectDesignPanel(page, "Routing");
  await expect(pitch).toHaveValue("2");
  await expect(page.getByRole("alert").filter({ hasText: "Magnet X length" })).toHaveCount(0);
});

test("odd magnet counts are accepted and step controls increment by one", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Magnets", exact: true }).click();
  const count = page.locator("#magnet-count");
  await expect(count).toHaveAttribute("min", "2");
  await expect(count).toHaveAttribute("max", "12");
  await expect(count).toHaveAttribute("step", "1");
  await count.fill("5");
  await count.press("Tab");
  await expect(count).toHaveValue("5");
  await expect(count).toHaveAttribute("aria-invalid", "false");
  await expect(page.getByText(/Magnet count must be/)).toHaveCount(0);
  await count.focus();
  await count.press("ArrowDown");
  await count.press("Tab");
  await expect(count).toHaveValue("4");
  await count.focus();
  await count.press("ArrowUp");
  await count.press("Tab");
  await expect(count).toHaveValue("5");
});

test("an over-limit magnet draft is rejected rather than clamping saved geometry", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Magnets", exact: true }).click();
  const count = page.locator("#magnet-count");
  await count.fill("5"); await count.press("Tab");
  await count.fill("13");
  await expect(count).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByRole("alert").filter({ hasText: "Value must be at most 12" })).toBeVisible();
  await count.press("Tab"); await expect(count).toHaveValue("5");
});
