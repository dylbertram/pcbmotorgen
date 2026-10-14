import { expect, test, type Page } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test.beforeEach(async ({ page }) => {
  // Only replace native dialogs and file transport. Rust tests cover disk safety.
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      window.__moves = [];
      export async function resolveDocumentPath(path) { return path; }
      export async function pickProjectDirectory() { return window.__cancelFolder ? null : window.__folder ?? '/Users/designer/Documents'; }
      export async function relocateProject(sourcePath, directory, name, project, activeVersionId) {
        if (window.__moveError) throw new Error(window.__moveError);
        const path = directory.replace(/\\/$/, '') + '/' + (name.endsWith('.pmmotor') ? name : name + '.pmmotor');
        window.__moves.push({ sourcePath, path });
        return { path, active_version_id: activeVersionId ?? 1, versions: [{ id: 1, description: '', created_at_unix_ms: 1, last_edited_at_unix_ms: 1 }], saved_at_unix_ms: 1, format_version: 2 };
      }`,
  }));
});

function activeFileTab(page: Page) {
  return page.getByRole("tablist", { name: "Coil files" }).getByRole("tab").first();
}

async function openRenameModal(page: Page) {
  await activeFileTab(page).click({ button: "right" });
  await page.getByRole("menuitem", { name: "Rename", exact: true }).click();
  return page.getByRole("form", { name: "File name and location" });
}

test("tab context menu Rename modal saves, renames and moves while keeping the unsaved draft", async ({ page }) => {
  await gotoDesignApp(page);
  const tab = activeFileTab(page);
  const form = await openRenameModal(page);
  const name = form.getByLabel("Name:");
  await expect(name).toBeFocused();
  await expect(name).toHaveValue("untitled.pmmotor");
  expect(await name.evaluate(el => [el.selectionStart, el.selectionEnd])).toEqual([0, 8]);
  await name.fill("Motor");
  await form.getByRole("button", { name: "Choose project folder" }).click();
  await expect(form.getByText("Documents", { exact: true })).toBeVisible();
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form).toBeHidden();
  await expect(tab).toContainText("Motor.pmmotor");

  await page.locator("#magnet-count").fill("8");
  await page.locator("#magnet-count").press("Enter");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
  await openRenameModal(page);
  await expect(name).toHaveValue("Motor.pmmotor");
  await name.fill("Motor revised.pmmotor");
  await name.press("Enter");
  await expect(form).toBeHidden();
  await expect(tab).toContainText("Motor revised.pmmotor");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
  await expect(page.locator("#magnet-count")).toHaveValue("8");
  await expect(page.getByRole("button", { name: "Project versions", exact: true })).toHaveText("Version 1");
  await openRenameModal(page);
  await page.evaluate(() => (window as any).__folder = "/Users/designer/Desktop");
  await form.getByRole("button", { name: "Choose project folder" }).click();
  await expect(form.getByText("Desktop", { exact: true })).toBeVisible();
  await form.getByRole("button", { name: "Apply", exact: true }).click();
  await expect(form).toBeHidden();
  await expect(tab).toHaveAttribute("title", "/Users/designer/Desktop/Motor revised.pmmotor");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as any).__moves)).toEqual([
    { sourcePath: null, path: "/Users/designer/Documents/Motor.pmmotor" },
    { sourcePath: "/Users/designer/Documents/Motor.pmmotor", path: "/Users/designer/Documents/Motor revised.pmmotor" },
    { sourcePath: "/Users/designer/Documents/Motor revised.pmmotor", path: "/Users/designer/Desktop/Motor revised.pmmotor" },
  ]);
});

test("cancel, Escape and clicking outside discard name and folder edits", async ({ page }) => {
  await gotoDesignApp(page);
  const tab = activeFileTab(page);
  for (const action of ["cancel", "escape", "outside"]) {
    const form = await openRenameModal(page);
    await expect(form.getByLabel("Name:")).toHaveValue("untitled.pmmotor");
    await form.getByLabel("Name:").fill("Discard this");
    if (action === "cancel") await form.getByRole("button", { name: "Cancel", exact: true }).click();
    else if (action === "escape") await page.keyboard.press("Escape");
    else await page.mouse.click(5, 5);
    await expect(form).toBeHidden();
    await expect(tab).toContainText("Untitled motor");
  }
  expect(await page.evaluate(() => (window as any).__moves)).toEqual([]);
});

test("invalid names, folder cancellation and file failures leave the modal open", async ({ page }) => {
  await gotoDesignApp(page);
  const tab = activeFileTab(page);
  const form = await openRenameModal(page);
  await form.getByLabel("Name:").fill("../Invalid");
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form.getByRole("alert")).toContainText("Enter a file name");
  await form.getByLabel("Name:").fill("Valid");
  await page.evaluate(() => (window as any).__cancelFolder = true);
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form).toBeVisible();
  expect(await page.evaluate(() => (window as any).__moves)).toEqual([]);
  await page.evaluate(() => { (window as any).__cancelFolder = false; (window as any).__moveError = "A file with this name already exists"; });
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form.getByRole("alert")).toContainText("already exists");
  await expect(tab).toContainText("Untitled motor");
  await expect(form.getByLabel("Name:")).toHaveValue("Valid");
});
