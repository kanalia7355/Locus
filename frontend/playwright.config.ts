import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const python = resolve(
  "..",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${python}" ../tests/e2e_server.py`,
      url: "http://127.0.0.1:8000/api/health",
      env: { PYTHONPATH: "../backend", LOCUS_E2E: "1" },
      reuseExistingServer: false,
      timeout: 60000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      timeout: 60000,
    },
  ],
});
