const { defineConfig } = require("@playwright/test");

const productionBaseUrl = String(process.env.SITE_BASE_URL || "").trim().replace(/\/$/, "");

module.exports = defineConfig({
  testDir: "./tests/browser",
  timeout: 45_000,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "line",
  use: {
    baseURL: productionBaseUrl || "http://127.0.0.1:4183",
    channel: "chrome",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: productionBaseUrl ? undefined : {
    command: "python3 server.py --bind 127.0.0.1 --port 4183",
    url: "http://127.0.0.1:4183/api/health",
    reuseExistingServer: false,
    timeout: 30_000
  }
});
