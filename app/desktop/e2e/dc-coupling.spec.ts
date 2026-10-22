import { test, expect, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

async function openPanel(page: Page, bridge = true) {
  await gotoDesignApp(page);
  await page.getByRole("tab", { name: /^Simulate/i }).click();
  if (bridge) await page.evaluate(() => {
    const w = window as any;
    w.dcMode = "completed"; w.dcInspectMode = "qualified"; w.dcCalls = [];
    w.__TAURI_INTERNALS__ = { invoke: async (command: string, args: any) => {
      if (command === "dc_coupling_capability") return { available: true, scope: "UI fixture only", qualified_cases: [
        {case_id:"fixture-case",label:"Fixture qualified design",audit_sha256:"fixture-audit",
         declaration:{material_model:{fixture:true},return_geometry:{fixture:true}}}] };
      w.dcCalls.push({command,args});
      if (command === "inspect_dc_coupling") {
        const qualified = w.dcInspectMode !== "preparation";
        const report = {schema:"finite-dc-applicability-v1",request_id:args.study.request_id,request_sha256:"inspection-content-hash",
          state:qualified ? "qualified" : "preparation-required",source_status:qualified ? "qualified-exact-basis" : "unqualified",
          force_status:qualified ? "qualified-sampled-states" : "unqualified",
          reason:qualified ? "The active copper matches this verified case. No force calculated." : "Actual copper requires its own offline preparation and qualification.",
          qualified_case:qualified ? {case_id:"fixture-case",label:"Fixture qualified design",audit_sha256:"fixture-audit"} : null};
        if (w.dcInspectMode === "delayed") return new Promise(resolve => {w.resolveDcInspection=()=>resolve(report);});
        return report;
      }
      if (command === "start_dc_coupling") {
        if (w.dcMode === "failed") throw new Error("Actual winding differs from qualified geometry");
        w.dcJob = {request_id:args.study.request_id,job_id:`job-${args.study.request_id}`,state:"running",
          request_sha256:"fresh-content-hash",elapsed_seconds:0,evidence_directory:"/test-ui-only",error:null,result:null};
        if (w.dcMode === "start-delayed") return new Promise(resolve => {w.resolveDcStart=()=>resolve(w.dcJob);});
        return w.dcJob;
      }
      if (command === "cancel_dc_coupling") return {...w.dcJob,state:"cancelled",result:null};
      if (command === "dc_coupling_status") {
        const qualified = {case_id:"fixture-case",label:"Fixture qualified design",audit_sha256:"fixture-audit"};
        const complete = {...w.dcJob,state:"completed",result:{status:"passed-fresh-qualified-geometry-dc-request-only",
          input_request_sha256:"fresh-content-hash",fresh_solution_sha256:"test-solution-hash",pm_array_force_n:[0.001,0.002,-1.1],
          qualified_case:qualified,eligibility:{request_id:w.dcJob.request_id,current_a:0.1,pm_offset_x_m:0,qualified_case:qualified}}};
        if (w.dcMode === "pending") return w.dcJob;
        if (w.dcMode === "poll-delayed") return new Promise(resolve=>{w.resolveDcPoll=()=>resolve(complete);});
        return complete;
      }
      throw new Error(`UI fixture has no ${command} calculation`);
    }};
  });
  await page.getByRole("tab", {name:"Static DC (experimental)",exact:true}).click();
  return page.getByRole("region", {name:"Experimental static DC coupling",exact:true});
}

async function declare(page: Page) {
  const panel = page.getByRole("region", {name:"Experimental static DC coupling",exact:true});
  await panel.getByRole("textbox", {name:"Explicit material placement and finite return (JSON, SI units)"})
    .fill('{"material_model":{},"return_geometry":{}}');
  await panel.getByRole("checkbox").check();
  return panel;
}

test("DC panel has no browser forces or implicit placement acknowledgement", async ({page})=>{
  const panel=await openPanel(page,false);
  await expect(panel).toContainText("requires the configured experimental desktop worker");
  await expect(panel.getByRole("button",{name:"Calculate static DC force",exact:true})).toBeDisabled();
  await expect(panel.getByRole("checkbox")).not.toBeChecked();
  await expect(panel.getByRole("textbox")).toHaveValue("");
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("DC UI separates fresh vector results and clears them on current changes",async({page},info)=>{
  const panel=await openPanel(page);await declare(page);
  await panel.getByRole("button",{name:"Calculate static DC force",exact:true}).click();
  await expect(panel.getByLabel("Fresh static DC force results")).toContainText("-1.10000 N");
  await expect(panel).toContainText("Componentwise relative accuracy and interpolation are not qualified");
  await panel.getByLabel("Fresh static DC force results").scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath("dc-explicit-force-panel.png")});
  await panel.getByRole("combobox",{name:"Loop current (A)"}).selectOption("0.1");
  await expect(panel.locator("dl")).toHaveCount(0);
  await page.evaluate(()=>{(window as any).dcMode="failed";});
  await panel.getByRole("button",{name:"Calculate static DC force",exact:true}).click();
  await expect(panel).toContainText("Actual winding differs from qualified geometry");
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("a DC start arriving after edits is cancelled without publishing a force",async({page})=>{
  const panel=await openPanel(page);await declare(page);
  await page.evaluate(()=>{(window as any).dcMode="start-delayed";});
  await panel.getByRole("button",{name:"Calculate static DC force",exact:true}).click();
  await expect(panel).toContainText("Calculating fresh fields");
  await panel.getByRole("combobox",{name:"PM lateral offset (µm)"}).selectOption("0.0001");
  await page.evaluate(()=>{(window as any).resolveDcStart();});
  await expect.poll(()=>page.evaluate(()=>(window as any).dcCalls.filter((c:any)=>c.command==="cancel_dc_coupling").length)).toBe(1);
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("late DC force cannot replace an edited or cancelled study",async({page})=>{
  const panel=await openPanel(page);await declare(page);
  await page.evaluate(()=>{(window as any).dcMode="poll-delayed";});
  await panel.getByRole("button",{name:"Calculate static DC force",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>typeof (window as any).resolveDcPoll)).toBe("function");
  await panel.getByRole("button",{name:"Cancel DC job",exact:true}).click();
  await expect(panel).toContainText("DC request cancelled");
  await page.evaluate(()=>{(window as any).resolveDcPoll();});
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("leaving the DC tab cancels its active numerical job",async({page})=>{
  const panel=await openPanel(page);await declare(page);
  await page.evaluate(()=>{(window as any).dcMode="pending";});
  await panel.getByRole("button",{name:"Calculate static DC force",exact:true}).click();
  await expect(panel).toContainText("Calculating fresh fields");
  await page.getByRole("tab",{name:"Summary (live metrics)",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).dcCalls.filter((c:any)=>c.command==="cancel_dc_coupling").length)).toBeGreaterThan(0);
});

test("DC declaration rejects archived forces or incomplete input",async({page})=>{
  const panel=await openPanel(page);await declare(page);
  await panel.getByRole("textbox").fill('{"material_model":{},"return_geometry":{},"force_n":5}');
  await panel.getByRole("button",{name:"Calculate static DC force",exact:true}).click();
  await expect(panel).toContainText("Do not include archived forces or winding snapshots");
  expect(await page.evaluate(()=>(window as any).dcCalls.filter((c:any)=>c.command==="start_dc_coupling").length)).toBe(0);
});

test("qualified designs fill only their audited placement and still need acknowledgement",async({page})=>{
  const panel=await openPanel(page);
  await expect(panel.getByRole("list",{name:"Qualified DC designs"})).toContainText("Fixture qualified design");
  await panel.getByRole("checkbox").check();
  await panel.getByRole("button",{name:"Use audited placement",exact:true}).click();
  await expect(panel.getByRole("textbox")).toHaveValue(/"fixture": true/);
  await expect(panel.getByRole("checkbox")).not.toBeChecked();
  await expect(panel.getByRole("button",{name:"Calculate static DC force",exact:true})).toBeDisabled();
  await panel.getByRole("checkbox").check();
  await panel.getByRole("button",{name:"Calculate static DC force",exact:true}).click();
  await expect(panel).toContainText("Qualified design: Fixture qualified design");
  const start=await page.evaluate(()=>(window as any).dcCalls.find((c:any)=>c.command==="start_dc_coupling"));
  expect(start.args.study.material_model).toEqual({fixture:true});
  expect(Object.keys(start.args.study)).not.toContain("winding");
});

test("checking the active design separates qualification from force calculation",async({page})=>{
  const panel=await openPanel(page);await declare(page);
  await panel.getByRole("button",{name:"Check this design",exact:true}).click();
  await expect(panel.getByLabel("Active design DC applicability")).toContainText("Qualified design");
  await expect(panel.getByLabel("Active design DC applicability")).toContainText("verified for this exact geometry");
  await expect(panel.locator("dl")).toHaveCount(0);
  expect(await page.evaluate(()=>(window as any).dcCalls.filter((c:any)=>c.command==="start_dc_coupling").length)).toBe(0);
});

test("unqualified designs need preparation and cannot calculate a fixture force",async({page})=>{
  const panel=await openPanel(page);await declare(page);
  await page.evaluate(()=>{(window as any).dcInspectMode="preparation";});
  await panel.getByRole("button",{name:"Check this design",exact:true}).click();
  await expect(panel.getByLabel("Active design DC applicability")).toContainText("Preparation required");
  await expect(panel.getByLabel("Active design DC applicability")).toContainText("Current source: unqualified");
  await expect(panel.getByRole("button",{name:"Calculate static DC force",exact:true})).toBeDisabled();
  await expect(panel.locator("dl")).toHaveCount(0);
});

test("a late applicability check cannot qualify edited geometry",async({page})=>{
  const panel=await openPanel(page);await declare(page);
  await page.evaluate(()=>{(window as any).dcInspectMode="delayed";});
  await panel.getByRole("button",{name:"Check this design",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>typeof (window as any).resolveDcInspection)).toBe("function");
  await panel.getByRole("combobox",{name:"Loop current (A)"}).selectOption("0.1");
  await page.evaluate(()=>{(window as any).resolveDcInspection();});
  await expect(panel.getByLabel("Active design DC applicability")).toHaveCount(0);
  await expect(panel.locator("dl")).toHaveCount(0);
});
