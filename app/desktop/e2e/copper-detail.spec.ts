import {test,expect,type Page} from "@playwright/test";

async function markerPixels(page:Page, image:Buffer):Promise<{size:number;x:number;y:number}[]> {
  return page.evaluate(async base64=>{
    const image=new Image();image.src=`data:image/png;base64,${base64}`;await image.decode();
    const canvas=document.createElement("canvas");canvas.width=image.width;canvas.height=image.height;
    const context=canvas.getContext("2d")!;context.drawImage(image,0,0);
    const {data}=context.getImageData(0,0,canvas.width,canvas.height),selected=new Set<number>();
    for(let i=0;i<data.length;i+=4) if(data[i]>30&&data[i]<80&&data[i+1]>190&&data[i+2]>130&&data[i+2]<175) selected.add(i/4);
    const markers:{size:number;x:number;y:number}[]=[];
    while(selected.size){
      const first=selected.values().next().value!;selected.delete(first);
      const queue=[first];let minX=canvas.width,maxX=0,minY=canvas.height,maxY=0;
      for(let i=0;i<queue.length;i++){
        const at=queue[i],x=at%canvas.width,y=Math.floor(at/canvas.width);
        minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);
        for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){
          if(x+dx<0||x+dx>=canvas.width||y+dy<0||y+dy>=canvas.height)continue;
          const next=at+dx+dy*canvas.width;
          if(selected.delete(next))queue.push(next);
        }
      }
      if(queue.length>=4)markers.push({size:Math.max(maxX-minX+1,maxY-minY+1),x:(minX+maxX)/2,y:(minY+maxY)/2});
    }
    return markers.sort((a,b)=>a.y-b.y);
  },image.toString("base64"));
}

test("coil-end markers stay small through zoom while solid annuli and trace cutouts render",async({page},info)=>{
  const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
  await page.goto("/");
  await page.evaluate(async()=>{
    const {renderCopperDetail}=await import(/* @vite-ignore */ "/e2e/fixtures/copperDetailHarness.ts");
    (window as any).closeCopperDetail=renderCopperDetail();
  });
  const fixture=page.getByTestId("physical-copper-detail"),viewer=fixture.getByTestId("coil-iso"),canvas=viewer.locator("canvas");
  await expect(viewer).toHaveAttribute("data-camera",/position/);
  await expect(viewer).toHaveAttribute("data-terminals","2");
  const masks=[viewer.getByRole("group",{name:"Z height",exact:true}),fixture.getByRole("group",{name:"Zoom controls",exact:true}),viewer.getByRole("img",{name:"Viewport axes: X travel, Y across board, Z up",exact:true})];
  const sizes=()=>canvas.screenshot({mask:masks,maskColor:"#ffffff"}).then(image=>markerPixels(page,image));
  await expect.poll(async()=> (await sizes()).length).toBe(2);
  // Center the end annotations before magnifying them. Correct extents no
  // longer include the hidden PCB body, so a zoom can otherwise crop the ends.
  const markers=await sizes(),rect=(await canvas.boundingBox())!;
  const center=markers.reduce((p,m)=>({x:p.x+m.x/markers.length,y:p.y+m.y/markers.length}),{x:0,y:0});
  await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.5);
  await page.mouse.down({button:"right"});
  await page.mouse.move(rect.x+rect.width-center.x,rect.y+rect.height-center.y,{steps:10});
  await page.mouse.up({button:"right"});
  for(const direction of ["initial","Zoom in","Zoom out"]){
    if(direction!=="initial")for(let i=0;i<3;i++)await fixture.getByRole("button",{name:direction,exact:true}).click();
    await expect.poll(async()=> (await sizes()).length).toBe(2);
    for(const {size} of await sizes()){expect(size).toBeGreaterThanOrEqual(6);expect(size).toBeLessThanOrEqual(9);}
  }
  await page.screenshot({path:info.outputPath("solid-annuli-trimmed-traces-and-end-markers.png")});
  await page.emulateMedia({colorScheme:"dark"});
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
  await page.screenshot({path:info.outputPath("solid-annuli-trimmed-traces-dark.png")});
  expect(errors).toEqual([]);
  await page.evaluate(async()=>{await (window as any).closeCopperDetail();});
});

test("small terminal annotations still pick exact physical centers rather than copper faces",async({page})=>{
  await page.goto("/");
  await page.evaluate(async()=>{
    const {renderCopperDetail}=await import(/* @vite-ignore */ "/e2e/fixtures/copperDetailHarness.ts");
    (window as any).closeCopperDetail=renderCopperDetail();
  });
  const fixture=page.getByTestId("physical-copper-detail"),viewer=fixture.getByTestId("coil-iso"),canvas=viewer.locator("canvas");
  await expect(viewer).toHaveAttribute("data-camera",/position/);
  await fixture.getByRole("button",{name:"Measure terminal centers",exact:true}).click();
  const masks=[viewer.getByRole("group",{name:"Z height",exact:true}),viewer.getByRole("img",{name:"Viewport axes: X travel, Y across board, Z up",exact:true})];
  const markers=await markerPixels(page,await canvas.screenshot({mask:masks,maskColor:"#ffffff"}));
  expect(markers).toHaveLength(2);
  const rect=(await canvas.boundingBox())!;
  for(const marker of markers)await page.mouse.click(rect.x+marker.x,rect.y+marker.y);
  await expect(viewer).toHaveAttribute("data-measure-points","2");
  await expect.poll(async()=>Number(await viewer.getAttribute("data-measure-mm"))).toBeCloseTo(.2475,10);
  await viewer.getByRole("slider",{name:"Z height scale",exact:true}).focus();
  await page.keyboard.press("End");
  await expect(viewer).toHaveAttribute("data-z-scale","20");
  await expect.poll(async()=>Number(await viewer.getAttribute("data-measure-mm"))).toBeCloseTo(.2475,10);
  await page.evaluate(async()=>{await (window as any).closeCopperDetail();});
});

test("through-via pads follow trace connections while plating crosses unconnected layers", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await page.evaluate(async () => {
    const { renderConnectedViaPads } = await import(/* @vite-ignore */ "/e2e/fixtures/copperDetailHarness.ts");
    (window as any).closeConnectedViaPads = renderConnectedViaPads();
  });
  const fixture = page.getByTestId("connected-via-pads");
  for (const [label, id] of [["Top-down", "top"], ["Front", "front"], ["Left", "left"], ["3D fields and heat", "iso"]]) {
    await fixture.getByRole("button", { name: label, exact: true }).click();
    const viewer = fixture.getByTestId(`coil-${id}`);
    await expect(viewer).toHaveAttribute("data-camera", /position/);
    await expect(viewer).toHaveAttribute("data-via-pads", "3");
    await expect(viewer).toHaveAttribute("data-vias", "1");
    await fixture.getByRole("checkbox", { name: "Hide branch connection", exact: true }).check();
    await expect(viewer).toHaveAttribute("data-via-pads", "2");
    await fixture.getByRole("checkbox", { name: "Hide branch connection", exact: true }).uncheck();
    // Isolating L2 leaves a full barrel but no trace or annulus on that layer.
    for (const layer of [1, 3, 4, 5, 6]) await fixture.getByRole("checkbox", { name: `Show layer ${layer}`, exact: true }).uncheck();
    await expect(viewer).toHaveAttribute("data-segments", "0");
    await expect(viewer).toHaveAttribute("data-via-pads", "0");
    await expect(viewer).toHaveAttribute("data-vias", "1");
    for (const layer of [1, 3, 4, 5, 6]) await fixture.getByRole("checkbox", { name: `Show layer ${layer}`, exact: true }).check();
    await expect(viewer).toHaveAttribute("data-via-pads", "3");
  }
  const viewer = fixture.getByTestId("coil-iso");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ path: info.outputPath("connected-annuli-physical-height.png") });
  await viewer.getByRole("slider", { name: "Z height scale", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(viewer).toHaveAttribute("data-z-scale", "20");
  await expect(viewer).toHaveAttribute("data-via-pads", "3");
  await page.screenshot({ path: info.outputPath("connected-annuli-continuous-barrel.png") });
  expect(errors).toEqual([]);
  await page.evaluate(async () => { await (window as any).closeConnectedViaPads(); });
});
