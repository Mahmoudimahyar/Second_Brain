import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    // Aurora is designed dark-first; with next-themes' enableSystem the
    // browser's color-scheme preference wins on first paint. Force dark
    // so axe-core measures contrast against the intended Aurora dark
    // tokens instead of the light-mode tokens running on a dark surface.
    colorScheme: "dark",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Auto-start the Next.js dev server for E2E. Skip in CI when a server
  // is already running (PLAYWRIGHT_NO_WEBSERVER=1).
  ...(process.env.PLAYWRIGHT_NO_WEBSERVER
    ? {}
    : {
        webServer: {
          command: "pnpm dev",
          url: "http://localhost:3000",
          reuseExistingServer: true,
          timeout: 120_000,
        },
      }),
});
