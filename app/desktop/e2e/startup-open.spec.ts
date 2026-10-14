import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("pcbmotorgen.recentProjects", JSON.stringify(["/designs/Motor.pmmotor"]));
  });
  await page.route(/\/src\/lib\/ipc\/routing\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/routing.ts?original';
      export async function listRoutingPatterns() { return [{ id: 'infinity-braid', display_name: 'Infinity Braid', min_layers: 6, max_layers: 6 }]; }
      export async function routingPatternParameters() { return []; }
      export async function loadInstalledPlugins() { return []; }`,
  }));
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      export async function fileExists() { return true; }
      export async function setRecentFiles() {}
      export async function resolveDocumentPath(path) { return path; }
      export async function pickProjectOpenPath() { return '/designs/Motor.pmmotor'; }
      export async function loadProject() {
        const { ConfigStore } = await import('/src/lib/stores/config.svelte.ts');
        const { MotionStore } = await import('/src/lib/stores/motion.svelte.ts');
        const { ProjectStore } = await import('/src/lib/stores/project.svelte.ts');
        const config = new ConfigStore();
        const project = new ProjectStore(config, new MotionStore(config)).snapshotIpc();
        project.config.magnet_count = 8;
        return { project, active_version_id: 1, versions: [], format_version: 1, source_format_version: 1, validation: { errors: [], warnings: [] } };
      }`,
  }));
});

for (const action of ["recent", "browse"] as const) {
  test(`startup ${action} opens a clean document after catalog loading`, async ({ page }) => {
    await page.goto("/");
    const startup = page.getByRole("region", { name: "Project workspace" });
    if (action === "recent") await startup.getByRole("button", { name: /Motor.pmmotor/ }).click();
    else await startup.getByRole("button", { name: "Open file or project…" }).click();
    await expect(startup).toBeHidden();
    await expect(page.locator("#num-layers")).toContainText("6");
    await expect(page.locator("#magnet-count")).toHaveValue("8");
    await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);
    await page.locator("#magnet-count").fill("10");
    await page.locator("#magnet-count").press("Enter");
    await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Close Motor.pmmotor" }).click();
    const confirm = page.getByRole("dialog", { name: "Save changes?" });
    await expect(confirm).toBeVisible();
    await confirm.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.locator("#magnet-count")).toHaveValue("10");
  });
}
