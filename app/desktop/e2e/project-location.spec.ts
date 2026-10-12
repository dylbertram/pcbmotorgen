import { expect, test } from "@playwright/test";
import { gotoDesignApp } from "./helpers";

test.beforeEach(async ({ page }) => {
  // Only replace native dialogs and file transport. Rust tests cover disk safety.
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      window.__moves = [];
      export async function pickProjectDirectory() { return window.__cancelFolder ? null : window.__folder ?? '/Users/designer/Documents'; }
      export async function relocateProject(sourcePath, directory, name, project, activeVersionId) {
        if (window.__moveError) throw new Error(window.__moveError);
        const path = directory.replace(/\\/$/, '') + '/' + (name.endsWith('.pmproj') ? name : name + '.pmproj');
        window.__moves.push({ sourcePath, path });
        return { path, active_version_id: activeVersionId ?? 1, versions: [{ id: 1, description: '', created_at_unix_ms: 1, last_edited_at_unix_ms: 1 }], saved_at_unix_ms: 1, format_version: 2 };
      }`,
  }));
});

test("title popover saves, renames and moves while keeping the unsaved draft", async ({ page }) => {
  await gotoDesignApp(page);
  const title = page.getByRole("button", { name: "Change project name and location" });
  await title.click();
  const form = page.getByRole("form", { name: "Project name and location" });
  const name = form.getByLabel("Name:");
  await expect(name).toBeFocused();
  await expect(name).toHaveValue("untitled.pmproj");
  expect(await name.evaluate(el => [el.selectionStart, el.selectionEnd])).toEqual([0, 8]);
  await name.fill("Motor");
  await form.getByRole("button", { name: "Choose project folder" }).click();
  await expect(form.getByText("Documents", { exact: true })).toBeVisible();
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form).toBeHidden();
  await expect(title).toContainText("Motor.pmproj");

  await page.locator("#magnet-count").fill("8");
  await page.locator("#magnet-count").press("Enter");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
  await title.click();
  await expect(name).toHaveValue("Motor.pmproj");
  await name.fill("Motor revised.pmproj");
  await name.press("Enter");
  await expect(form).toBeHidden();
  await expect(title).toContainText("Motor revised.pmproj");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
  await expect(page.locator("#magnet-count")).toHaveValue("8");
  await expect(page.getByRole("button", { name: "Project versions", exact: true })).toHaveText("Version 1");
  await title.click();
  await page.evaluate(() => (window as any).__folder = "/Users/designer/Desktop");
  await form.getByRole("button", { name: "Choose project folder" }).click();
  await expect(form.getByText("Desktop", { exact: true })).toBeVisible();
  await form.getByRole("button", { name: "Apply", exact: true }).click();
  await expect(form).toBeHidden();
  await expect(title).toHaveAttribute("title", "/Users/designer/Desktop/Motor revised.pmproj");
  await expect(page.getByLabel("Unsaved changes", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as any).__moves)).toEqual([
    { sourcePath: null, path: "/Users/designer/Documents/Motor.pmproj" },
    { sourcePath: "/Users/designer/Documents/Motor.pmproj", path: "/Users/designer/Documents/Motor revised.pmproj" },
    { sourcePath: "/Users/designer/Documents/Motor revised.pmproj", path: "/Users/designer/Desktop/Motor revised.pmproj" },
  ]);
});

test("cancel, Escape and clicking outside discard name and folder edits", async ({ page }) => {
  await gotoDesignApp(page);
  const title = page.getByRole("button", { name: "Change project name and location" });
  const form = page.getByRole("form", { name: "Project name and location" });
  for (const action of ["cancel", "escape", "outside"]) {
    await title.click();
    await expect(form.getByLabel("Name:")).toHaveValue("untitled.pmproj");
    await form.getByLabel("Name:").fill("Discard this");
    if (action === "cancel") await form.getByRole("button", { name: "Cancel", exact: true }).click();
    else if (action === "escape") await page.keyboard.press("Escape");
    else await page.locator("#tab-design").click();
    await expect(form).toBeHidden();
    await expect(title).toContainText("untitled design");
  }
  expect(await page.evaluate(() => (window as any).__moves)).toEqual([]);
});

test("invalid names, folder cancellation and file failures leave the popover open", async ({ page }) => {
  await gotoDesignApp(page);
  const title = page.getByRole("button", { name: "Change project name and location" });
  await title.click();
  const form = page.getByRole("form", { name: "Project name and location" });
  await form.getByLabel("Name:").fill("../Invalid");
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form.getByRole("alert")).toContainText("Enter a project name");
  await form.getByLabel("Name:").fill("Valid");
  await page.evaluate(() => (window as any).__cancelFolder = true);
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form).toBeVisible();
  expect(await page.evaluate(() => (window as any).__moves)).toEqual([]);
  await page.evaluate(() => { (window as any).__cancelFolder = false; (window as any).__moveError = "A file with this name already exists"; });
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(form.getByRole("alert")).toContainText("already exists");
  await expect(title).toContainText("untitled design");
  await expect(form.getByLabel("Name:")).toHaveValue("Valid");
});
