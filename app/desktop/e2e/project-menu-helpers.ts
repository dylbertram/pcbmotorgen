import type { Page } from "@playwright/test";

/** Replace only native menu transport; application handlers remain real. */
export async function installFileActionMenu(page: Page): Promise<void> {
  await page.route(/\/src\/lib\/menu\/projectMenu\.ts(?:\?t=\d+)?$/, route => route.fulfill({
    contentType: "application/javascript",
    body: `export async function bindProjectMenuActions(handlers) {
      const handle = event => handlers[event.detail]?.();
      window.addEventListener('test-file-action', handle);
      return () => window.removeEventListener('test-file-action', handle);
    }`,
  }));
}
