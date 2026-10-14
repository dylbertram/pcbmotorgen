import { expect, test, type Page } from "@playwright/test";

// Only the disk/dialog transport is replaced. Stores, tabs and revision UI are
// production code; Rust tests cover the actual files and migration.
test.beforeEach(async ({ page }) => {
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      const clone = value => JSON.parse(JSON.stringify(value));
      const disk = window.__disk = {};
      let serial = 0, time = 1700000000000;
      window.__savePaths = [];
      export async function resolveDocumentPath(path) { return path; }
      export async function pickProjectSavePath(name, kind) {
        if (window.__savePaths.length) return window.__savePaths.shift();
        return '/coil-' + (++serial) + (kind === 'sensor' ? '.pmsensor' : '.pmmotor');
      }
      export async function pickWorkspaceSavePath() { return '/project.pmproj'; }
      export async function pickProjectOpenPath() { return window.__openPath ?? '/project.pmproj'; }
      export async function saveProject(path, project, options) {
        const archive = clone(disk[options.sourcePath] ?? { versions: [], next: 1 });
        let version = archive.versions.find(v => v.id === options.activeVersionId);
        if (!version || options.newVersion) {
          version = { id: archive.next++, created_at_unix_ms: ++time, description: options.description ?? '' };
          archive.versions.push(version);
        }
        version.project = clone(project);
        version.last_edited_at_unix_ms = ++time;
        archive.kind = options.kind;
        disk[path] = archive;
        return { path, versions: archive.versions.map(({project,...info}) => info), active_version_id: version.id, format_version: 1, saved_at_unix_ms: time };
      }
      export async function loadProject(path, id) {
        const archive = disk[path];
        if (!archive) throw Error('File not found: ' + path);
        const version = id ? archive.versions.find(v => v.id === id) : [...archive.versions].sort((a,b) => b.last_edited_at_unix_ms - a.last_edited_at_unix_ms)[0];
        return { project: clone(version.project), versions: archive.versions.map(({project,...info}) => info), active_version_id: version.id, format_version: 1, source_format_version: 1, validation: { errors: [], warnings: [] } };
      }
      export async function saveWorkspace(path, files, activeFile) { disk[path] = { path, files: [...files], active_file: activeFile, legacy: false }; }
      export async function loadWorkspace(path) { if (!disk[path]) throw Error('File not found'); return clone(disk[path]); }
      export async function bindProjectMenuActions(handlers) {
        window.__fileAction = (name) => handlers[name]?.();
        return () => {};
      }`,
  }));
});

async function create(page: Page, kind: "motor" | "sensor") {
  await page.getByRole("button", { name: "New coil file", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "New coil file", exact: true });
  await dialog.getByRole("button", { name: kind === "motor" ? /^Motor coil/ : /^Sensor coil/ }).click();
  await expect(dialog).toBeHidden();
}

async function fileAction(page: Page, name: string) {
  await page.evaluate(name => (window as any).__fileAction(name), name);
}

test("multiple motor and sensor tabs keep separate drafts and dirty markers", async ({ page }) => {
  await page.goto("/");
  await create(page, "motor");
  await page.locator("#magnet-count").fill("6");
  await page.locator("#magnet-count").press("Enter");
  await create(page, "motor");
  await expect(page.locator("#magnet-count")).toHaveValue("12");
  await page.locator("#magnet-count").fill("8");
  await page.locator("#magnet-count").press("Enter");
  await create(page, "sensor");
  await expect(page.getByRole("tab", { name: /^Simulate/ })).toHaveCount(0);
  await page.locator("#sensor-wavelength").fill("240");
  await page.locator("#sensor-wavelength").press("Enter");
  const tabs = page.getByRole("navigation", { name: "Open files" });
  await tabs.getByRole("tab", { name: /^M Untitled motor 1/ }).click();
  await expect(page.locator("#magnet-count")).toHaveValue("6");
  await tabs.getByRole("tab", { name: /^M Untitled motor 2/ }).click();
  await expect(page.locator("#magnet-count")).toHaveValue("8");
  await tabs.getByRole("tab", { name: /^S Untitled sensor 3/ }).click();
  await expect(page.locator("#sensor-wavelength")).toHaveValue("240");
  await expect(tabs.getByLabel("Unsaved changes", { exact: true })).toHaveCount(3);
});

test("Save All and workspace reopen preserve separate files and the active tab", async ({ page }) => {
  await page.goto("/");
  await create(page, "motor");
  await page.locator("#magnet-count").fill("6");
  await page.locator("#magnet-count").press("Enter");
  await create(page, "sensor");
  await page.locator("#sensor-wavelength").fill("240");
  await page.locator("#sensor-wavelength").press("Enter");
  await fileAction(page, "saveAll");
  await expect(page.getByRole("navigation", { name: "Open files" }).getByLabel("Unsaved changes")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (window as any).__disk['/project.pmproj'])).toEqual({ path: "/project.pmproj", files: ["/coil-1.pmmotor", "/coil-2.pmsensor"], active_file: "/coil-2.pmsensor", legacy: false });
  await fileAction(page, "newProject");
  await expect(page.getByRole("region", { name: "Project workspace" })).toBeVisible();
  await fileAction(page, "open");
  await expect(page.locator("#sensor-wavelength")).toHaveValue("240");
  await page.getByRole("navigation", { name: "Open files" }).getByRole("tab", { name: /M coil-1.pmmotor/ }).click();
  await expect(page.locator("#magnet-count")).toHaveValue("6");
});

test("Save new version revises the active file without creating another tab", async ({ page }) => {
  await page.goto("/");
  await create(page, "motor");
  await fileAction(page, "save");
  await expect(page.getByRole("button", { name: "Project versions", exact: true })).toHaveText("Version 1");
  await page.locator("#magnet-count").fill("8");
  await page.locator("#magnet-count").press("Enter");
  await fileAction(page, "saveNewVersion");
  const versions = page.getByRole("dialog", { name: "Project versions", exact: true });
  await versions.getByLabel("Description", { exact: true }).fill("Eight magnets");
  await versions.getByRole("button", { name: "Save new version", exact: true }).click();
  await expect(versions).toBeHidden();
  await expect(page.getByRole("button", { name: "Project versions", exact: true })).toHaveText("Version 2");
  const archive = await page.evaluate(() => (window as any).__disk['/coil-1.pmmotor']);
  expect(archive.kind).toBe("motor");
  expect(archive.versions.map((v: any) => v.project.config.magnet_count)).toEqual([12, 8]);
  await expect(page.getByRole("navigation", { name: "Open files" }).getByRole("button", { name: /^Close/ })).toHaveCount(1);
});

test("close and New Project offer save, discard and cancel without losing a canceled draft", async ({ page }) => {
  await page.goto("/");
  await create(page, "motor");
  await page.locator("#magnet-count").fill("6");
  await page.locator("#magnet-count").press("Enter");
  await page.getByRole("button", { name: "Close Untitled motor 1", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Save changes?" });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.locator("#magnet-count")).toHaveValue("6");
  await page.evaluate(() => { (window as any).__savePaths = [null]; });
  await page.getByRole("button", { name: "Close Untitled motor 1", exact: true }).click();
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.locator("#magnet-count")).toHaveValue("6");
  await fileAction(page, "newProject");
  dialog = page.getByRole("dialog", { name: "Save changes?" });
  await dialog.getByRole("button", { name: "Discard", exact: true }).click();
  await expect(page.getByRole("region", { name: "Project workspace" })).toBeVisible();
});
