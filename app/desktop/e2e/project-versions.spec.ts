import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test.beforeEach(async ({ page }) => {
  // Replace only disk/menu transport. Rust tests exercise the real archive and files.
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, (route) => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      let versions = [], nextId = 1, time = 1700000000000;
      const clone = value => JSON.parse(JSON.stringify(value));
      const summaries = () => versions.map(({ project, ...info }) => clone(info));
      const latest = () => [...versions].sort((a,b) => b.last_edited_at_unix_ms - a.last_edited_at_unix_ms)[0];
      window.__seedVersions = count => {
        while (versions.length < count) {
          const project = clone(latest().project), id = nextId++;
          versions.push({ id, description: 'Saved design ' + id, project, created_at_unix_ms: (time += 1000), last_edited_at_unix_ms: time });
        }
      };
      const result = id => {
        const version = versions.find(v => v.id === id) ?? latest();
        return { project: clone(version.project), active_version_id: version.id, versions: summaries(), format_version: 2, source_format_version: 2, validation: { errors: [], warnings: [] } };
      };
      export async function pickProjectSavePath() { return '/design.pmmotor'; }
      export async function pickProjectOpenPath() { return '/design.pmmotor'; }
      export async function resolveDocumentPath(path) { return path; }
      export async function saveProject(path, project, options) {
        time += 1000;
        let version = versions.find(v => v.id === options.activeVersionId);
        if (options.newVersion || !version) {
          version = { id: nextId++, created_at_unix_ms: time, description: options.description ?? '' };
          versions.push(version);
        }
        version.project = clone(project);
        version.last_edited_at_unix_ms = time;
        window.__versions = clone(versions);
        return { path, active_version_id: version.id, versions: summaries(), saved_at_unix_ms: time, format_version: 2 };
      }
      export async function loadProject(path, id) { return result(id); }
      export async function updateProjectVersion(path, id, active, options) {
        if (options.deleteVersion) versions = versions.filter(v => v.id !== id);
        else { const v = versions.find(v => v.id === id); v.description = options.description; v.last_edited_at_unix_ms = (time += 1000); }
        window.__versions = clone(versions);
        return result(active);
      }
      export async function bindProjectMenuActions(handlers) {
        const handle = event => handlers[event.detail]?.();
        window.addEventListener('test-file-action', handle);
        return () => window.removeEventListener('test-file-action', handle);
      }`,
  }));
});

async function fileAction(page: Page, action: string) {
  await page.evaluate(action => window.dispatchEvent(new CustomEvent("test-file-action", { detail: action })), action);
}

async function newVersion(page: Page, description: string) {
  await fileAction(page, "saveNewVersion");
  const dialog = page.getByRole("dialog", { name: "Project versions", exact: true });
  await expect(dialog.getByRole("heading", { name: "Save new version", exact: true })).toBeVisible();
  await dialog.getByLabel("Description", { exact: true }).fill(description);
  await dialog.getByRole("button", { name: "Save new version", exact: true }).click();
  await expect(dialog).toBeHidden();
}

async function versionsDialog(page: Page) {
  await page.getByRole("button", { name: "Project versions", exact: true }).click();
  return page.getByRole("dialog", { name: "Project versions", exact: true });
}

test("title bar versions, File save-new-version, and latest-edited reopening", async ({ page }) => {
  await gotoDesignApp(page);
  let dialog = await versionsDialog(page);
  await expect(dialog.getByText(/No saved versions yet/)).toBeVisible();
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await newVersion(page, "Original design");
  await expect(page.getByRole("button", { name: "Project versions", exact: true })).toHaveText("Version 1");
  await page.locator("#magnet-count").fill("6");
  await page.locator("#magnet-count").press("Enter");
  await newVersion(page, "Six magnets");
  dialog = await versionsDialog(page);
  await expect(dialog.getByText("Created", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Last edited", { exact: true })).toBeVisible();
  await expect(dialog.getByLabel("Description", { exact: true })).toHaveValue("Six magnets");
  await dialog.getByRole("button", { name: /^Version 1/ }).click();
  await dialog.getByRole("button", { name: "Open version", exact: true }).click();
  await expect(page.locator("#magnet-count")).toHaveValue("12");
  await page.locator("#magnet-count").fill("8");
  await page.locator("#magnet-count").press("Enter");
  await fileAction(page, "save");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);
  await fileAction(page, "closeFile");
  await fileAction(page, "open");
  await expect(page.getByRole("button", { name: "Project versions", exact: true })).toHaveText("Version 1");
  await expect(page.locator("#magnet-count")).toHaveValue("8");
  const archive = await page.evaluate(() => (window as any).__versions);
  expect(archive).toHaveLength(2);
  expect(archive[0].created_at_unix_ms).toBeLessThan(archive[1].created_at_unix_ms);
  expect(archive[0].last_edited_at_unix_ms).toBeGreaterThan(archive[1].last_edited_at_unix_ms);
  expect(archive[1].project.config.magnet_count).toBe(6);
});

test("description edits and selective deletion preserve unsaved work", async ({ page }) => {
  await gotoDesignApp(page);
  await newVersion(page, "Original");
  await newVersion(page, "Alternative");
  await page.locator("#magnet-count").fill("8");
  await page.locator("#magnet-count").press("Enter");
  const dialog = await versionsDialog(page);
  await dialog.getByRole("button", { name: /^Version 1/ }).click();
  await dialog.getByLabel("Description", { exact: true }).fill("Baseline");
  await dialog.getByRole("button", { name: "Save description", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Save description", exact: true })).toBeDisabled();
  page.once("dialog", prompt => prompt.dismiss());
  await dialog.getByRole("button", { name: "Open version", exact: true }).click();
  await expect(dialog).toBeVisible();
  await expect(page.locator("#magnet-count")).toHaveValue("8");
  page.once("dialog", prompt => prompt.accept());
  await dialog.getByRole("button", { name: "Delete version", exact: true }).click();
  await expect(dialog.getByRole("button", { name: /^Version 1/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Delete version", exact: true })).toBeDisabled();
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.locator("#magnet-count")).toHaveValue("8");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
});

test("deleting the active version opens the remaining design", async ({ page }) => {
  await gotoDesignApp(page);
  await newVersion(page, "Original");
  await page.locator("#magnet-count").fill("6");
  await page.locator("#magnet-count").press("Enter");
  await newVersion(page, "Six magnets");
  const dialog = await versionsDialog(page);
  page.once("dialog", prompt => prompt.accept());
  await dialog.getByRole("button", { name: "Delete version", exact: true }).click();
  await expect(page.getByRole("button", { name: "Project versions", exact: true })).toHaveText("Version 1");
  await expect(dialog.getByLabel("Description", { exact: true })).toHaveValue("Original");
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.locator("#magnet-count")).toHaveValue("12");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toHaveCount(0);
});

test("long histories keep version details and actions in bounds on desktop and mobile", async ({ page }) => {
  await gotoDesignApp(page);
  await newVersion(page, "Original");
  await page.evaluate(() => (window as any).__seedVersions(25));
  await fileAction(page, "closeFile");
  await fileAction(page, "open");
  await expect(page.getByRole("button", { name: "Project versions", exact: true })).toHaveText("Version 25");
  const dialog = await versionsDialog(page);
  for (const width of [page.viewportSize()!.width, 375]) {
    await page.setViewportSize({ width, height: 640 });
    const list = dialog.getByRole("complementary", { name: "Saved versions", exact: true });
    expect(await list.evaluate(el => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
    await dialog.getByRole("button", { name: /^Version 1\b/ }).click();
    await expect(dialog.getByRole("heading", { name: "Version 1", exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Open version", exact: true })).toBeInViewport();
    const bounds = (await dialog.boundingBox())!;
    expect(bounds.y).toBeGreaterThanOrEqual(15);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(625);
    expect(bounds.x).toBeGreaterThanOrEqual(15);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width - 15);
  }
});
