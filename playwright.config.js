// Playwright config for the unified-map E2E tests.
// App served locally: API on :8010, static on :8080. One chromium project;
// individual tests set their own viewport (1440x900 / 1024x768 / 390x844).
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 90000,
  expect: { timeout: 20000 },
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8080",
    actionTimeout: 20000,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
  },
});
