import {test,expect,type Page} from "@playwright/test";
import {gotoDesignApp,openCoilPreview} from "./helpers";

async function copperBottom(page:Page,image:Buffer):Promise<number>{
  return page.evaluate(async base64=>{
    const image=new Image();image.src=`data:image/png;base64,${base64}`;await image.decode();
    const canvas=document.createElement("canvas");canvas.width=image.width;canvas.height=image.height;
    const context=canvas.getContext("2d")!;context.drawImage(image,0,0);
    const {data}=context.getImageData(0,0,canvas.width,canvas.height);
    for(let y=canvas.height-1;y>=0;y--)for(let x=0;x<canvas.width;x++){
      const i=(y*canvas.width+x)*4;
      if(Math.max(data[i],data[i+1],data[i+2])-Math.min(data[i],data[i+1],data[i+2])>40)return y;
    }
    return -1;
  },image.toString("base64"));
}

test("3D copper draws into the bottom control row instead of clipping above it",async({page},info)=>{
  await gotoDesignApp(page);await openCoilPreview(page);
  await page.getByRole("button",{name:"3D fields and heat",exact:true}).click();
  const frame=page.getByRole("img",{name:"Coil preview",exact:true});
  const viewer=page.getByTestId("coil-iso"),canvas=viewer.locator("canvas");
  await expect(viewer).toHaveAttribute("data-camera",/position/);
  await expect.poll(async()=>{
    const drawing=(await canvas.boundingBox())!,workspace=(await frame.boundingBox())!;
    return Math.abs(drawing.y+drawing.height-workspace.y-workspace.height);
  }).toBeLessThanOrEqual(1);
  const rect=(await canvas.boundingBox())!;
  const masks=[viewer.getByRole("group",{name:"Z height",exact:true}),page.getByRole("group",{name:"Zoom controls",exact:true}),
    page.getByRole("group",{name:"Viewport view",exact:true}),viewer.getByLabel("Simulation overlay legend")];
  const bottom=()=>canvas.screenshot({mask:masks,maskColor:"#ffffff"}).then(image=>copperBottom(page,image));
  const initial=await bottom();expect(initial).toBeGreaterThan(0);
  // Bring real copper into the last 40 px, formerly excluded by a 56 px strip.
  const delta=rect.height-16-initial;
  await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.5);
  await page.mouse.down({button:"right"});
  // Move left too, so the low corner is not hidden by the local view buttons.
  await page.mouse.move(rect.x+rect.width*.25,rect.y+rect.height*.5+delta,{steps:8});
  await page.mouse.up({button:"right"});
  await expect.poll(bottom).toBeGreaterThan(rect.height-40);
  await page.screenshot({path:info.outputPath("copper-through-bottom-control-row.png")});
});

test("mobile spatial views keep the full drawing height with controls layered above it",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await gotoDesignApp(page);await openCoilPreview(page);
  for(const [label,id] of [["3D fields and heat","iso"],["Front","front"],["Left","left"]]){
    await page.getByRole("button",{name:label,exact:true}).click();
    const canvas=page.getByTestId(`coil-${id}`).locator("canvas");
    const frame=page.getByRole("img",{name:"Coil preview",exact:true});
    await expect.poll(async()=>{
      const c=(await canvas.boundingBox())!,f=(await frame.boundingBox())!;
      return Math.abs(c.y+c.height-f.y-f.height);
    }).toBeLessThanOrEqual(1);
    const menu=page.getByRole("group",{name:"Zoom controls",exact:true});
    await expect(menu).toBeVisible();
    const c=(await canvas.boundingBox())!,m=(await menu.boundingBox())!;
    expect(m.y+m.height).toBeLessThanOrEqual(c.y+c.height);
  }
});
