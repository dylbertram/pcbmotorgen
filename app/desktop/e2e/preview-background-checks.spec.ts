import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp, selectDesignPanel } from "./helpers";

async function holdBackgroundWork(page: Page) {
  await page.addInitScript(() => {
    (window as any).previewWork = { drc: [], envelopes: [], previews: [], holdCounts: [], heldPreviews: [] };
  });
  await page.route(/\/src\/lib\/ipc\/routing\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/routing.ts?original';
      export function checkCoilInterference(config) {
        return new Promise((resolve, reject) => window.previewWork.drc.push({config:JSON.parse(JSON.stringify(config)), resolve, reject}));
      }`,
  }));
  await page.route(/\/src\/lib\/ipc\/physics\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/physics.ts?original';
      import { generateCoils as generate } from '/src/lib/ipc/physics.ts?original';
      export async function generateCoils(config) {
        const result = await generate(config);
        window.previewWork.previews.push({count:config.magnet_count, paths:result.phases.reduce((sum,p)=>sum+p.segments.length+(p.corner_arcs?.length??0),0)});
        if (window.previewWork.holdCounts.includes(config.magnet_count)) await new Promise(resolve => window.previewWork.heldPreviews.push({count:config.magnet_count, resolve}));
        return result;
      }
      export function fetchTravelEnvelope(config) {
        return new Promise((resolve, reject) => window.previewWork.envelopes.push({config:JSON.parse(JSON.stringify(config)), resolve, reject}));
      }`,
  }));
  await gotoDesignApp(page);
  await page.getByRole("button", { name: "3D fields and heat", exact: true }).click();
  await expect(page.getByTestId("coil-iso").locator("canvas")).toBeVisible();
  await expect.poll(() => page.evaluate(() => [(window as any).previewWork.drc.length, (window as any).previewWork.envelopes.length])).toEqual([1, 1]);
  await selectDesignPanel(page, "Magnets");
}

async function expectRenderedCount(page: Page, count: number) {
  await expect.poll(() => page.evaluate(count => (window as any).previewWork.previews.findLast((p: any) => p.count === count)?.paths, count)).toBeGreaterThan(0);
  const paths = await page.evaluate(count => (window as any).previewWork.previews.findLast((p: any) => p.count === count).paths, count);
  await expect(page.getByTestId("coil-iso")).toHaveAttribute("data-segments", String(paths));
}

test("3D trace updates start immediately while DRC and equilibrium remain unresolved", async ({ page }) => {
  await holdBackgroundWork(page);
  const now = new Date("2026-10-31T12:00:00Z");
  await page.clock.install({ time: now }); await page.clock.pauseAt(now);
  await page.getByRole("spinbutton", { name: "Magnet count", exact: true }).fill("8");
  // No 150 ms quiet period and no background completion is needed to publish geometry.
  await page.clock.runFor(50);
  await expectRenderedCount(page, 8);
  await expect(page.getByRole("button", { name: "Design rule check: DRC checking", exact: true })).toBeVisible();
  expect(await page.evaluate(() => [(window as any).previewWork.drc.length, (window as any).previewWork.envelopes.length])).toEqual([1, 1]);
});

test("edits redraw 3D copper while stale checks coalesce, and failures never roll it back", async ({ page }) => {
  await holdBackgroundWork(page);
  for (const count of [10, 8, 6]) {
    await page.getByRole("spinbutton", { name: "Magnet count", exact: true }).fill(String(count));
    await expectRenderedCount(page, count);
  }
  // Let the background debounce expire with the first call still unresolved.
  await page.clock.install(); await page.clock.fastForward(500);
  expect(await page.evaluate(() => [(window as any).previewWork.drc.length, (window as any).previewWork.envelopes.length])).toEqual([1, 1]);
  await page.evaluate(() => {
    const work = (window as any).previewWork;
    work.drc[0].resolve([]);
    work.envelopes[0].reject(new Error("Old envelope failure"));
  });
  await expect.poll(() => page.evaluate(() => [(window as any).previewWork.drc.length, (window as any).previewWork.envelopes.length])).toEqual([2, 2]);
  expect(await page.evaluate(() => [(window as any).previewWork.drc[1].config.magnet_count, (window as any).previewWork.envelopes[1].config.magnet_count])).toEqual([6, 6]);
  await expect(page.getByRole("button", { name: "Design rule check: DRC checking", exact: true })).toBeVisible();
  await expectRenderedCount(page, 6);
  await page.evaluate(() => (window as any).previewWork.drc[1].reject(new Error("Latest DRC failure")));
  await expect(page.getByRole("button", { name: "Design rule check: DRC failed", exact: true })).toBeVisible();
  await page.getByRole("spinbutton", { name: "Magnet count", exact: true }).fill("4");
  await expectRenderedCount(page, 4);
});

test("a late geometry response cannot replace newer traces while background checks are pending", async ({ page }) => {
  await holdBackgroundWork(page);
  await page.evaluate(() => (window as any).previewWork.holdCounts.push(10));
  await page.getByRole("spinbutton", { name: "Magnet count", exact: true }).fill("10");
  await expect.poll(() => page.evaluate(() => (window as any).previewWork.heldPreviews.length)).toBe(1);
  await page.getByRole("spinbutton", { name: "Magnet count", exact: true }).fill("6");
  await expectRenderedCount(page, 6);
  await page.evaluate(() => (window as any).previewWork.heldPreviews[0].resolve());
  await expectRenderedCount(page, 6);
  await expect(page.getByRole("button", { name: "Design rule check: DRC checking", exact: true })).toBeVisible();
});
