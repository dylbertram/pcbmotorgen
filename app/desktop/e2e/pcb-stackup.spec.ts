import { test, expect } from "@playwright/test";
import { gotoDesignApp, selectDesignPanel, openCoilPreview } from "./helpers";

for (const width of [1280, 390]) test(`Stackup copper weights seed custom layers and retain values at ${width}px`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 844 });
  await gotoDesignApp(page);
  await expect(page.getByTestId("coil-top").locator("canvas")).toBeVisible();
  await selectDesignPanel(page, "Stackup");
  const stackup = page.getByRole("dialog", { name: "Stackup", exact: true });
  const outer = stackup.getByRole("combobox", { name: "Outer layer copper weight", exact: true });
  const inner = stackup.getByRole("combobox", { name: "Inner layer copper weight", exact: true });
  await expect(outer.locator("option")).toHaveText(["0.5 oz", "1 oz", "2 oz", "3 oz"]);
  await outer.selectOption("2"); await inner.selectOption("0.5");
  await page.screenshot({ path: info.outputPath(`stackup-copper-${width}.png`) });
  await stackup.getByRole("checkbox", { name: "Define each layer thickness", exact: true }).check();
  await expect(outer).toBeDisabled(); await expect(inner).toBeDisabled();
  for (const [layer, thickness] of [[1, "70"], [2, "17.5"], [3, "17.5"], [4, "70"]] as const) {
    await expect(stackup.getByRole("spinbutton", { name: `Layer ${layer} copper thickness (µm)`, exact: true })).toHaveValue(thickness);
  }
  const copper = stackup.getByRole("spinbutton", { name: "Layer 2 copper thickness (µm)", exact: true });
  await copper.fill("25"); await copper.press("Enter");
  await selectDesignPanel(page, "Routing");
  const routing = page.getByRole("dialog", { name: "Routing", exact: true });
  const vias = routing.getByRole("figure", { name: "Via sizing guide", exact: true });
  const plating = vias.getByRole("spinbutton", { name: "Via plating thickness (µm)", exact: true });
  await plating.fill("40"); await plating.press("Enter");
  await plating.scrollIntoViewIfNeeded();
  await expect(routing.getByRole("combobox", { name: /layer copper weight/ })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath(`routing-vias-${width}.png`) });
  await selectDesignPanel(page, "Stackup");
  await expect(copper).toHaveValue("25");
  await expect(outer).toHaveValue("2"); await expect(inner).toHaveValue("0.5");
  await expect(outer).toBeDisabled(); await expect(inner).toBeDisabled();
  await stackup.getByRole("checkbox", { name: "Define each layer thickness", exact: true }).uncheck();
  await expect(outer).toBeEnabled(); await expect(inner).toBeEnabled();
  await expect(outer).toHaveValue("2"); await expect(inner).toHaveValue("0.5");
  await selectDesignPanel(page, "Routing"); await expect(plating).toHaveValue("40");
});

test("custom copper and dielectric thicknesses set the physical layer centers and board total", async ({ page }, info) => {
  await gotoDesignApp(page);
  await selectDesignPanel(page,"Stackup");
  await page.getByRole("spinbutton", { name:"PCB thickness (mm)", exact:true }).fill("0.8");
  await page.getByRole("spinbutton", { name:"PCB thickness (mm)", exact:true }).press("Enter");
  await page.getByRole("checkbox", {name:"Define each layer thickness",exact:true}).check();
  for (const [i,value] of [[1,"35"],[2,"18"],[3,"70"],[4,"35"]] as const) {
    const field=page.getByRole("spinbutton",{name:`Layer ${i} copper thickness (µm)`,exact:true});
    await field.fill(value); await field.press("Enter");
  }
  for (const [i,value] of [[1,"0.1"],[2,"0.4"],[3,"0.142"]] as const) {
    const field=page.getByRole("spinbutton",{name:`Dielectric ${i} thickness (mm)`,exact:true});
    await field.fill(value); await field.press("Enter");
  }
  await expect(page.getByLabel("PCB thickness (mm)",{exact:true})).toHaveText("0.8 mm");
  await openCoilPreview(page);
  await page.getByRole("button",{name:"3D fields and heat",exact:true}).click();
  const viewer=page.getByTestId("coil-iso");
  await expect(viewer.locator("canvas")).toBeVisible();
  await expect.poll(async()=>JSON.parse((await viewer.getAttribute("data-layer-z-mm"))!)[2]).toBeCloseTo(-.588,10);
  const heights=JSON.parse((await viewer.getAttribute("data-layer-z-mm"))!);
  [-.0175,-.144,-.588,-.7825].forEach((z,i)=>expect(heights[i]).toBeCloseTo(z,10));
  await page.screenshot({path:info.outputPath("custom-pcb-stackup.png")});
  await selectDesignPanel(page,"Stackup");
  await page.getByRole("checkbox",{name:"Define each layer thickness",exact:true}).uncheck();
  await expect(page.getByRole("spinbutton",{name:"PCB thickness (mm)",exact:true})).toHaveValue("0.8");
});

test("layer-count changes report a custom-stack mismatch until explicitly reset",async({page})=>{
  await gotoDesignApp(page);
  await selectDesignPanel(page,"Stackup");
  await page.getByRole("checkbox",{name:"Define each layer thickness",exact:true}).check();
  await selectDesignPanel(page,"Routing");
  await page.getByRole("button",{name:"Copper layer count",exact:true}).click();
  await page.getByRole("option",{name:"6",exact:true}).click();
  await selectDesignPanel(page,"Stackup");
  await expect(page.getByRole("alert").filter({hasText:"6 copper layers"})).toBeVisible();
  await page.getByRole("button",{name:"Reset for 6 layers",exact:true}).click();
  await expect(page.getByRole("spinbutton",{name:"Layer 6 copper thickness (µm)",exact:true})).toBeVisible();
  await expect(page.getByRole("alert").filter({hasText:"6 copper layers"})).toHaveCount(0);
});
