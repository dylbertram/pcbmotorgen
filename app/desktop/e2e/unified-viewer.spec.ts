import {test,expect} from "@playwright/test";
import {gotoDesignApp,openCoilPreview} from "./helpers";
import {installViewMenu,nativeViewAction} from "./view-menu-helpers";

test.beforeEach(async({page})=>{await installViewMenu(page);});

test("Top, Front, Left and 3D share one canvas, retain display state and restore navigation",async({page},info)=>{
  await gotoDesignApp(page);await openCoilPreview(page);
  const top=page.getByTestId("coil-top");
  await expect(top).toHaveAttribute("data-renderer","shared-three");
  await expect(top).toHaveAttribute("data-camera",/position/);
  const copper=top.locator("canvas");
  await copper.evaluate(el=>el.setAttribute("data-shared-instance","retained"));
  const originalCount=Number(await top.getAttribute("data-segments"));
  await nativeViewAction(page,"view:one-period");
  await expect.poll(async()=>Number(await top.getAttribute("data-segments"))).toBeLessThan(originalCount);
  const count=await top.getAttribute("data-segments");
  await nativeViewAction(page,"view:pcb");
  for(const [label,id,axis] of [["Front","front",2],["Left","left",0],["3D fields and heat","iso",-1],["Top-down","top",1]] as const) {
    await page.getByRole("button",{name:label,exact:true}).click();
    const viewer=page.getByTestId(`coil-${id}`);
    await expect(viewer.locator("canvas")).toHaveAttribute("data-shared-instance","retained");
    await expect(viewer).toHaveAttribute("data-pcb-visible","true");
    await expect(viewer).toHaveAttribute("data-segments",count!);
    await expect(viewer).toHaveAttribute("data-camera",/position/);
    if(axis>=0) await expect.poll(async()=>{
      const s=JSON.parse((await viewer.getAttribute("data-camera"))!);
      const d=s.position.map((v:number,i:number)=>v-s.target[i]);return Math.abs(d[axis])/Math.hypot(...d);
    }).toBeCloseTo(1,8);
    if(id==="iso") {
      await viewer.getByRole("button",{name:"Zoom in 3D",exact:true}).click();
      await page.screenshot({path:info.outputPath("shared-isometric.png")});
    }
  }
  await expect(page.getByTestId("coil-annotations")).toBeVisible();
  await page.screenshot({path:info.outputPath("shared-top-with-annotations.png")});
});

test("orthographic views use the spatial measure and zoom-window toolbar without enabling edits",async({page})=>{
  await gotoDesignApp(page);await openCoilPreview(page);
  for(const label of ["Front","Left"]){
    await page.getByRole("button",{name:label,exact:true}).click();
    await expect(page.getByRole("button",{name:"Edit segments",exact:true})).toBeDisabled();
    await page.getByRole("button",{name:"Toggle measure tool",exact:true}).click();
    await expect(page.getByRole("button",{name:"Toggle measure tool",exact:true})).toHaveAttribute("aria-pressed","true");
    await page.getByRole("button",{name:"Zoom window",exact:true}).click();
    await expect(page.getByRole("button",{name:"Pick zoom window corners",exact:true})).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button",{name:"Pick zoom window corners",exact:true})).toHaveCount(0);
  }
});

test("each view restores its own pan and zoom after visiting every other view",async({page})=>{
  await gotoDesignApp(page);await openCoilPreview(page);
  type Snapshot={position:number[];target:number[];zoom:number};
  const saved=new Map<string,Snapshot>();
  const modes=[["Top-down","top"],["Front","front"],["Left","left"],["3D fields and heat","iso"]] as const;
  for(const [label,id] of modes){
    await page.getByRole("button",{name:label,exact:true}).click();
    const viewer=page.getByTestId(`coil-${id}`);
    await expect(viewer).toHaveAttribute("data-camera",/position/);
    const before=JSON.parse((await viewer.getAttribute("data-camera"))!) as Snapshot;
    await page.getByRole("button",{name:id==="top"?"Zoom in":"Zoom in 3D",exact:true}).click();
    await expect.poll(async()=>JSON.parse((await viewer.getAttribute("data-camera"))!).zoom).toBeGreaterThan(before.zoom);
    const box=(await viewer.boundingBox())!;
    await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);
    await page.mouse.down({button:id==="top"?"middle":"right"});
    await page.mouse.move(box.x+box.width*.55,box.y+box.height*.55,{steps:5});
    await page.mouse.up({button:id==="top"?"middle":"right"});
    await expect.poll(async()=>JSON.parse((await viewer.getAttribute("data-camera"))!).target).not.toEqual(before.target);
    // Let OrbitControls finish damping before recording the navigation state.
    let last="";
    await expect.poll(async()=>{
      const current=(await viewer.getAttribute("data-camera"))!;
      const same=current===last;last=current;return same;
    }).toBe(true);
    saved.set(id,JSON.parse(last));
  }
  for(const [label,id] of modes){
    await page.getByRole("button",{name:label,exact:true}).click();
    const expected=saved.get(id)!;
    await expect.poll(async()=>{
      const actual=JSON.parse((await page.getByTestId(`coil-${id}`).getAttribute("data-camera"))!) as Snapshot;
      // OrbitControls stops emitting change events before its damping tail is
      // exactly zero. Bound that residual in screen pixels, not scene units.
      return Math.max(...actual.position.map((v,i)=>Math.abs(v-expected.position[i])),...actual.target.map((v,i)=>Math.abs(v-expected.target[i])))*actual.zoom;
    },{message:`${id} pan must restore within a quarter pixel`}).toBeLessThan(.25);
    await expect.poll(async()=>JSON.parse((await page.getByTestId(`coil-${id}`).getAttribute("data-camera"))!).zoom).toBeCloseTo(expected.zoom,10);
  }
});
