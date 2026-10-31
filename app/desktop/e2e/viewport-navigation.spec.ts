import { test, expect } from "@playwright/test";
import { gotoDesignApp, openCoilPreview } from "./helpers";
import { installViewMenu, nativeViewAction } from "./view-menu-helpers";

test.beforeEach(async ({ page }) => { await installViewMenu(page); });

test("all views share bottom-right navigation and top-left view presets", async ({ page }, info) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  for (const viewport of [{width:1280,height:800},{width:390,height:844}]) {
    await page.setViewportSize(viewport);
    let previous: {x:number;y:number;width:number;height:number} | null = null;
    for (const [label,id] of [["Top-down","top"],["Front","front"],["Left","left"],["3D fields and heat","iso"]]) {
      await page.getByRole("button",{name:label,exact:true}).click();
      const viewer=page.getByTestId(`coil-${id}`);
      await expect(viewer).toHaveAttribute("data-camera",/position/);
      await expect(page.getByText(/Drag to (orbit|pan)|Two-finger scroll to pan|Pinch to zoom/)).toHaveCount(0);
      const controls=page.getByRole("group",{name:"Zoom controls",exact:true});
      await controls.getByRole("button",{name:"Reset view",exact:true}).click();
      await expect.poll(async()=>Number(await controls.getByRole("button",{name:"Reset zoom",exact:true}).innerText().then(text=>text.replace("×","")))).toBe(1);
      const frame=(await page.getByRole("img",{name:"Coil preview",exact:true}).boundingBox())!;
      const presets=(await page.getByRole("group",{name:"Viewport view",exact:true}).boundingBox())!;
      const box=(await controls.boundingBox())!;
      const toolbar=page.getByRole("toolbar",{name:"Coil preview tools",exact:true});
      const tools=(await toolbar.boundingBox())!;
      await expect(toolbar.getByRole("group",{name:"Viewport view",exact:true})).toHaveCount(0);
      expect(presets.x).toBeCloseTo(frame.x+52,0);
      expect(presets.y).toBeCloseTo(tools.y+tools.height+8,0);
      const drawing=(await viewer.boundingBox())!;
      expect(presets.y+presets.height).toBeLessThan(drawing.y+drawing.height);
      if(id!=="top") {
        expect(presets.x).toBeCloseTo(drawing.x+8,0); expect(presets.y).toBeCloseTo(drawing.y+8,0);
        const zRail=(await viewer.getByRole("group",{name:"Z height",exact:true}).boundingBox())!;
        expect(zRail.y).toBeGreaterThanOrEqual(presets.y+presets.height+6);
      }
      expect(box.x+box.width).toBeCloseTo(frame.x+frame.width-56,0);
      expect(box.y+box.height).toBeCloseTo(frame.y+frame.height-12,0);
      if(previous) {
        expect(box.x+box.width).toBeCloseTo(previous.x+previous.width,0);
        expect(box.y).toBeCloseTo(previous.y,0);
      }
      previous=box;
      await expect(controls.getByRole("button",{name:"Zoom extents",exact:true})).toHaveCount(0);
      for(const name of ["Zoom out","Reset zoom","Zoom in","Zoom window","Reset view"])
        await expect(controls.getByRole("button",{name,exact:true})).toBeVisible();
      await expect(controls.getByRole("button",{name:"Zoom window",exact:true}).locator("svg circle")).toHaveCount(1);
      const initial=JSON.parse((await viewer.getAttribute("data-camera"))!);
      await controls.getByRole("button",{name:"Zoom in",exact:true}).click();
      await expect.poll(async()=>JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeGreaterThan(initial.zoom);
      await controls.getByRole("button",{name:"Reset zoom",exact:true}).click();
      await expect.poll(async()=>JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeCloseTo(initial.zoom,6);
      await controls.getByRole("button",{name:"Zoom in",exact:true}).click();
      await expect.poll(async()=>JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeGreaterThan(initial.zoom);
      await controls.getByRole("button",{name:"Reset view",exact:true}).click();
      await expect.poll(async()=>JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeCloseTo(initial.zoom,6);
    }
    await page.screenshot({path:info.outputPath(`shared-controls-${viewport.width}.png`)});
    await page.emulateMedia({colorScheme:"dark"});
    await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
    await page.screenshot({path:info.outputPath(`shared-controls-${viewport.width}-dark.png`)});
    await page.emulateMedia({colorScheme:"light"});
  }
});

test("off-center window sets a copper-depth pivot and orbit stays around it", async ({ page }, info) => {
  await gotoDesignApp(page); await openCoilPreview(page);
  await page.getByRole("button",{name:"3D fields and heat",exact:true}).click();
  const viewer=page.getByTestId("coil-iso"), controls=page.getByRole("group",{name:"Zoom controls",exact:true});
  await expect(viewer).toHaveAttribute("data-camera",/position/);
  const snapshot=async()=>JSON.parse((await viewer.getAttribute("data-camera"))!) as {position:number[];target:number[];zoom:number};
  const initial=await snapshot();
  const direction=(s:typeof initial)=>{const d=s.position.map((v,i)=>v-s.target[i]);return d.map(v=>v/Math.hypot(...d));};
  for(const [a,b] of [[[.5,.35],[.7,.55]],[[.35,.35],[.55,.55]]] as [number[],number[]][]) {
    const before=await snapshot();
    await controls.getByRole("button",{name:"Zoom window",exact:true}).click();
    const picker=page.getByRole("button",{name:"Pick zoom window corners",exact:true});
    const rect=(await picker.boundingBox())!;
    await page.mouse.click(rect.x+rect.width*a[0],rect.y+rect.height*a[1]);
    await page.mouse.click(rect.x+rect.width*b[0],rect.y+rect.height*b[1]);
    await expect(picker).toHaveCount(0);
    await expect.poll(async()=>(await snapshot()).zoom).toBeGreaterThan(before.zoom);
    const fitted=await snapshot();
    expect(fitted.target).not.toEqual(before.target);
    direction(fitted).forEach((v,i)=>expect(v).toBeCloseTo(direction(before)[i],9));
    const zs=JSON.parse((await viewer.getAttribute("data-layer-z-mm"))!) as number[];
    const scale=Number(await viewer.getAttribute("data-trace-width-px"))/fitted.zoom/Number(await viewer.getAttribute("data-trace-width-mm"));
    expect(Math.abs(fitted.target[1])).toBeLessThanOrEqual((Math.max(...zs)-Math.min(...zs)+.1)*scale/2);
    // A real orbit must change the camera position without returning to the old pivot.
    await page.mouse.move(rect.x+rect.width*.8,rect.y+rect.height*.75);
    await page.mouse.down(); await page.mouse.move(rect.x+rect.width*.85,rect.y+rect.height*.68,{steps:10}); await page.mouse.up();
    await expect.poll(async()=>(await snapshot()).position).not.toEqual(fitted.position);
    await expect.poll(async()=>(await snapshot()).target.map(v=>Math.round(v*1e8))).toEqual(fitted.target.map(v=>Math.round(v*1e8)));
    // Compare the fitted angle to a settled orbit, not an earlier animation frame.
    let previous=direction(await snapshot()), stable=0;
    await expect.poll(async()=>{
      const next=direction(await snapshot()),delta=Math.hypot(...next.map((v,i)=>v-previous[i]));
      previous=next; stable=delta<1e-7?stable+1:0; return stable;
    },{timeout:10000}).toBeGreaterThanOrEqual(2);
    const orbited=await snapshot();
    await nativeViewAction(page,"view:zoom-extents");
    await expect.poll(async()=>Math.hypot(...(await snapshot()).target)).toBeLessThan(.1);
    await expect.poll(async()=>(await snapshot()).zoom).toBeLessThan(fitted.zoom);
    // OrbitControls stops emitting below its change-event epsilon even while
    // subpixel damping remains. Allow <0.006 degrees between those snapshots.
    expect(Math.hypot(...direction(await snapshot()).map((v,i)=>v-direction(orbited)[i]))).toBeLessThan(1e-4);
  }
  await controls.getByRole("button",{name:"Reset view",exact:true}).click();
  await expect.poll(async()=>(await snapshot()).zoom).toBeCloseTo(initial.zoom,6);
  direction(await snapshot()).forEach((v,i)=>expect(v).toBeCloseTo(direction(initial)[i],9));
  await page.screenshot({path:info.outputPath("reset-after-off-center-orbit.png")});
});
