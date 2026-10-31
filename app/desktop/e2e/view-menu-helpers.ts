import { expect, type Page } from "@playwright/test";
import type { ViewMenuState } from "../src/lib/viewMenu";

/** Exercise the real menu controller at its native IPC boundary in Chromium. */
export async function installViewMenu(page: Page): Promise<void> {
  await page.route(/\/src\/lib\/ipc\/viewMenu\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export async function publishViewMenu(state) { window.__nativeViewMenu = state; }
      export async function listenViewMenu(handler) {
        const listener = e => handler(e.detail); window.addEventListener('native-view-action', listener);
        return () => window.removeEventListener('native-view-action', listener);
      }`,
  }));
}

export const viewMenuSnapshot = (page: Page) => page.evaluate(() => (window as any).__nativeViewMenu as ViewMenuState);
export const viewMenuChecked = async (page: Page, id: string) => (await viewMenuSnapshot(page))?.items.find(item => item.id === id)?.checked;

export async function nativeViewAction(page: Page, id: string, owner?: string): Promise<void> {
  await page.evaluate(({ id, owner }) => window.dispatchEvent(new CustomEvent("native-view-action", {
    detail: { id, owner: owner ?? (window as any).__nativeViewMenu.owner },
  })), { id, owner });
}

export async function setViewMenuChecked(page: Page, id: string, checked: boolean): Promise<void> {
  await expect.poll(async () => (await viewMenuSnapshot(page))?.items.find(item => item.id === id)?.enabled).toBe(true);
  if (await viewMenuChecked(page, id) !== checked) await nativeViewAction(page, id);
  await expect.poll(() => viewMenuChecked(page, id)).toBe(checked);
}
