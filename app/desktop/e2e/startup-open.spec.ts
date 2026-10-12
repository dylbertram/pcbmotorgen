import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("pcbmotorgen.recentProjects", JSON.stringify(["/designs/Motor.pmproj"]));
  });
  // Force asynchronous catalog initialization to change the default layer count.
  await page.route(/\/src\/lib\/ipc\/routing\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/routing.ts?original';
      export async function listRoutingPatterns() {
        return [{ id: 'infinity-braid', display_name: 'Infinity Braid', min_layers: 6, max_layers: 6 }];
      }
      export async function routingPatternParameters() { return []; }
      export async function loadInstalledPlugins() { return []; }`,
  }));
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      window.__discardPrompts = 0;
      export async function fileExists() { return true; }
      export async function setRecentFiles() {}
      export async function pickProjectOpenPath() { return '/designs/Motor.pmproj'; }
      export async function confirmDiscardChanges() { window.__discardPrompts++; return false; }
      export async function loadProject() {
        const { config } = await import('/src/lib/stores/config.svelte.ts');
        const { MotionStore } = await import('/src/lib/stores/motion.svelte.ts');
        const { ProjectStore } = await import('/src/lib/stores/project.svelte.ts');
        const project = new ProjectStore(config, new MotionStore(config)).snapshotIpc();
        project.config.magnet_count = 8;
        return { project, active_version_id: 1, versions: [], format_version: 2, source_format_version: 2, validation: { errors: [], warnings: [] } };
      }
      export async function bindProjectMenuActions(handlers) {
        const handle = event => handlers[event.detail]?.();
        window.addEventListener('test-file-action', handle);
        return () => window.removeEventListener('test-file-action', handle);
      }`,
  }));
});

for (const action of ["recent", "selected recent", "browse"] as const) {
  test(`startup ${action} opens without a discard prompt, but later edits remain protected`, async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await expect(startup).toBeVisible();
    await expect(page.locator("#num-layers")).toContainText("6");
    await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);
    if (action !== "browse") {
      const recent = startup.getByRole("button", { name: /Motor.pmproj/ });
      if (action === "recent") await recent.dblclick();
      else {
        await recent.click();
        await startup.getByRole("button", { name: "Open", exact: true }).click();
      }
    } else {
      await startup.getByRole("button", { name: "Open project…" }).click();
    }
    await expect(startup).toBeHidden();
    await expect(page.getByRole("status", { name: "Project notification" })).toHaveCount(0);
    await expect(page.getByText(/^Opened /)).toHaveCount(0);
    expect(await page.evaluate(() => (window as any).__discardPrompts)).toBe(0);
    await expect(page.locator("#magnet-count")).toHaveValue("8");
    await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);

    await page.locator("#magnet-count").fill("10");
    await page.locator("#magnet-count").press("Enter");
    await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("test-file-action", { detail: "open" })));
    await expect.poll(() => page.evaluate(() => (window as any).__discardPrompts)).toBe(1);
    await expect(page.locator("#magnet-count")).toHaveValue("10");
  });
}
