import { test, expect } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("via guide distinguishes hole diameter from ring width and updates live", async ({ page }) => {
  await gotoDesignApp(page);
  const hole = page.getByRole("spinbutton", { name: "Via hole size (mm)", exact: true });
  const ring = page.getByRole("spinbutton", { name: "Annular ring width (mm)", exact: true });
  await hole.fill("0.2");
  await hole.blur();
  await ring.fill("0.05");
  await ring.blur();
  const guide = page.getByRole("figure", { name: "Via sizing guide" });
  expect(await guide.evaluate((element) => Math.abs(element.getBoundingClientRect().width - element.parentElement!.getBoundingClientRect().width))).toBeLessThan(1);
  const diameter = guide.locator("dl > div").filter({ hasText: "Via diameter" }).locator("dd");
  await expect(diameter).toHaveText("0.300 mm");
  await ring.fill("0.075");
  await ring.blur();
  await expect(diameter).toHaveText("0.350 mm");
  await expect(guide.getByRole("img")).toBeVisible();
  const graphicBox = (await guide.getByRole("img").boundingBox())!;
  const inputBox = (await ring.boundingBox())!;
  expect(inputBox.x + inputBox.width).toBeLessThan(graphicBox.x);
  await expect(guide.getByText("Ring width, each side", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("spinbutton", { name: "Strands per phase", exact: true })).toHaveCount(0);
  await expect(page.getByText("Via diameter = hole size + 2 × ring width.", { exact: false })).toHaveCount(0);
  await page.getByRole("button", { name: "About via diameter", exact: true }).focus();
  await expect(page.getByText("Via diameter = hole size + 2 × ring width.", { exact: false })).toBeVisible();
  await expect(page.getByText("Allow at least 0.10 mm extra diameter;", { exact: false })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "About annular ring width", exact: true }).focus();
  await expect(page.getByText("Copper width on one side of the hole.", { exact: false })).toBeVisible();
});

test("CAD import shares the same via sizing guide and help", async ({ page }) => {
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "File", exact: true }).click();
  await page.getByRole("menuitem", { name: "Import CAD…" }).click();
  const dialog = page.getByRole("dialog", { name: "Import CAD" });
  await dialog.getByText("Via sizes", { exact: true }).click();
  await dialog.getByRole("textbox", { name: "Via hole size (mm)", exact: true }).fill("0.2");
  await dialog.getByRole("textbox", { name: "Annular ring width (mm)", exact: true }).fill("0.075");
  const guide = dialog.getByRole("figure", { name: "Via sizing guide" });
  await expect(guide.locator("dl > div").filter({ hasText: "Via diameter" }).locator("dd")).toHaveText("0.350 mm");
  const graphicBox = (await guide.getByRole("img").boundingBox())!;
  const inputBox = (await dialog.getByRole("textbox", { name: "Annular ring width (mm)", exact: true }).boundingBox())!;
  expect(inputBox.x + inputBox.width).toBeLessThan(graphicBox.x);
  await dialog.getByRole("button", { name: "About via hole size", exact: true }).focus();
  await expect(page.getByText("The diameter of the drilled hole, excluding", { exact: false })).toBeVisible();
});
