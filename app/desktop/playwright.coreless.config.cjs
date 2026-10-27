// Isolated coreless regression server; never reuse an unrelated dev checkout.
// Use Node 24 and a fresh CORELESS_BROWSER_ARTIFACTS folder to preserve failures.
const path = require("node:path");
const artifacts = process.env.CORELESS_BROWSER_ARTIFACTS || path.join(__dirname, "e2e-results/coreless");
const port = Number(process.env.CORELESS_BROWSER_PORT || 1451);
if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error("Invalid coreless browser port");
const url = `http://127.0.0.1:${port}`;
module.exports = {
  testDir: path.join(__dirname, "e2e"),
  outputDir: path.join(artifacts, "tests"),
  reporter: [["list"], ["json", { outputFile: path.join(artifacts, "report.json") }]],
  use: { baseURL: url, browserName: "chromium", headless: true, screenshot: "only-on-failure" },
  projects: [
    { name: "desktop-tauri", use: { viewport: { width: 1280, height: 800 } } },
    { name: "desktop-wide", use: { viewport: { width: 1600, height: 1000 } } },
  ],
  webServer: {
    command: `pnpm exec vite --host 127.0.0.1 --port ${port} --strictPort`,
    cwd: __dirname, url, reuseExistingServer: false, timeout: 60000,
  },
};
