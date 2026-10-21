import { expect, test } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

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
