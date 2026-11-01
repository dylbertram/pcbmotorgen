import { expect, test } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("electrical pitch cannot be committed below twice the magnet length", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "Magnets", exact: true }).click();
  const width = page.locator("#magnet-width");
  await expect(width).toHaveAttribute("max", "6");
  await width.fill("5"); await width.press("Tab");
  await page.getByRole("button", { name: "Routing", exact: true }).click();
  const pitch = page.locator("#electrical-pitch");
  await expect(pitch).toHaveAttribute("min", "10");
  await expect(pitch).toHaveAttribute("max", "20");
  await pitch.fill("9");
  await expect(pitch).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByRole("alert").filter({ hasText: "Value must be at least 10" })).toBeVisible();
  await pitch.press("Tab"); await expect(pitch).toHaveValue("12");
  await pitch.fill("10"); await pitch.press("Tab");
  await expect(pitch).toHaveValue("10");
  await page.getByRole("button", { name: "Magnets", exact: true }).click();
  await expect(width).toHaveValue("5");
  await expect(width).toHaveAttribute("max", "5");
  await width.fill("5.1"); await expect(width).toHaveAttribute("aria-invalid", "true");
  await width.press("Tab"); await expect(width).toHaveValue("5");
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
