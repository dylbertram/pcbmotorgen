import { expect, test } from "@playwright/test";

test("startup sends existing recent projects to the native menu on every launch", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("pcbmotorgen.recentProjects", JSON.stringify(["/designs/Motor.pmproj"]));
  });
  // Observe the native-menu transport without replacing the recents store.
  await page.route(/\/src\/lib\/ipc\/project\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export * from '/src/lib/ipc/project.ts?original';
      window.__recentMenuUpdates = [];
      export async function fileExists() { return true; }
      export async function setRecentFiles(paths) { window.__recentMenuUpdates.push([...paths]); }`,
  }));
  await page.goto("/");
  for (let launch = 0; launch < 2; launch++) {
    if (launch > 0) await page.reload();
    const startup = page.getByRole("dialog", { name: "Recent projects" });
    await expect(startup.getByRole("button", { name: /Motor.pmproj/ })).toBeVisible();
    await expect.poll(() => page.evaluate(() => (window as any).__recentMenuUpdates)).toEqual([["/designs/Motor.pmproj"]]);
  }
});
