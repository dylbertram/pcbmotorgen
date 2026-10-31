import { expect, test } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test("carriage mass defaults to magnets, supports a complete assembly override and copies into a move draft", async ({ page }, testInfo) => {
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
  await page.getByRole("tab", { name: "Power requirements", exact: true }).click();
  const power = page.getByRole("region", { name: "Power requirements", exact: true });
  await power.locator("summary").filter({ hasText: "Move definition and calculation" }).click();
  const editor = power.getByRole("textbox", { name: "Move model JSON", exact: true });
  expect(JSON.parse(await editor.inputValue()).profile.moving_mass_kg).toBeNull();
  await power.getByRole("button", { name: "Use design mass and friction", exact: true }).click();
  const move = JSON.parse(await editor.inputValue());
  expect(move.profile.moving_mass_kg).toBe(0.015);
  expect(move.profile.coulomb_friction_n).toBe(0.06);
  expect(move.profile.mass_includes).toContain("Full moving assembly estimate");
  expect(move.profile.duration_s).toBeNull();
  expect(move.source.accepts_regeneration).toBeNull();
  await expect(power).toContainText("Unapplied move draft");
});
