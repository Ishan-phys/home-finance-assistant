import { defineConfig } from "@playwright/test";

// End-to-end tests drive the running stack: `docker compose up -d` first. They empty the
// database before each test, so never point them at data you want to keep.
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  workers: 1,
  timeout: 60_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000", screenshot: "only-on-failure" },
  reporter: [["list"]],
});
