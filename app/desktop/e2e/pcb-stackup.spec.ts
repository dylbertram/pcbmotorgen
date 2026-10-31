import { test, expect } from "@playwright/test";
import { gotoDesignApp, selectDesignPanel, openCoilPreview } from "./helpers";

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
