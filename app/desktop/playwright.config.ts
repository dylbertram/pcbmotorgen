import { defineConfig, devices } from "@playwright/test";

/**
 * Visual-layout e2e suite for the pcbmotorgen desktop UI.
 *
 * The Tauri shell is NOT required: every IPC call is gated behind
 * `isTauriAvailable()` in `src/lib/tauri.ts`, and the browser falls back to
 * deterministic mocks, so the full layout renders under Vite. This lets us
 * verify geometry invariants (column alignment, scrollbar position, panel
 * restructure) without `tauri-driver` — which has no free macOS WKWebView
 * driver (CrabNebula's fork is paid).
 */
export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e-results",
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: "http://localhost:1420",
    // Use Playwright's bundled Chromium so CI/server runs need no system Chrome.
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      // Matches the Tauri window (1280×800 family) — the `lg` layout applies.
      name: "desktop-tauri",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    {
      // Wide layout — right column reaches the window edge.
      name: "desktop-wide",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 1000 } },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:1420",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
