import { expect, test } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("carriage mass defaults to magnets and the move form uses the complete assembly override", async ({ page }, testInfo) => {
  await gotoDesignApp(page);
  const tools = page.getByRole("toolbar", { name: "Design side tools", exact: true });
  await tools.getByRole("button", { name: "Magnets", exact: true }).click();
  for (const [label, value] of [
    ["X Length (mm), magnet length along the travel axis", "5"],
    ["Y Width (mm), magnet width across the stator", "5"],
    ["Z Thickness (mm), magnetisation-axis thickness", "3"],
    ["Magnet count", "10"],
  ]) {
    const field = page.getByRole("spinbutton", { name: label, exact: true });
    await field.fill(value);
    await field.press("Enter");
  }
  await page.locator("#magnet-grade").click();
  await page.getByRole("option", { name: "N52", exact: true }).click();
  await tools.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  const carriage = page.getByRole("region", { name: "Carriage mass and friction", exact: true });
  await expect(carriage).toContainText("Carriage mass: 5.70 g");
  await expect(carriage.getByRole("table", { name: "Magnet mass breakdown" })).toContainText("0.57 g");
  await expect(carriage).toContainText("User-supplied reference");
  await carriage.getByLabel("Carriage mass basis", { exact: true }).selectOption("assembly");
  const mass = carriage.getByRole("spinbutton", { name: "Full carriage mass (g)", exact: true });
  await mass.fill("15");
  await mass.press("Enter");
  const friction = carriage.getByRole("spinbutton", { name: "Friction estimate (N)", exact: true });
  await friction.fill("0.06");
  await friction.press("Enter");
  await page.screenshot({ path: testInfo.outputPath("carriage-assembly.png") });
  await tools.getByRole("button", { name: "Magnets", exact: true }).click();
  await page.getByRole("spinbutton", { name: "Magnet count", exact: true }).fill("12");
  await page.getByRole("spinbutton", { name: "Magnet count", exact: true }).press("Enter");
  await tools.getByRole("button", { name: "Drive & force targets", exact: true }).click();
  await expect(carriage.getByRole("spinbutton", { name: "Full carriage mass (g)", exact: true })).toHaveValue("15");
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  const power = page.getByRole("region", { name: "Move and power", exact: true });
  await expect(power).toContainText("15.00 g full moving assembly");
  await expect(power).toContainText("0.060 N sliding friction");
  await power.getByRole("button", { name: "Edit load", exact: true }).click();
  await expect(power.getByRole("spinbutton", { name: "Move moving mass in grams", exact: true })).toHaveValue("15");
  await expect(power.getByRole("spinbutton", { name: "Move friction in newtons", exact: true })).toHaveValue("0.06");
  await power.getByRole("button", { name: "Use design load", exact: true }).click();
  await expect(power).toContainText("15.00 g full moving assembly");
});
