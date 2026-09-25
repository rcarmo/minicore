import { defineConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";
export default defineConfig({
  testDir: defineBddConfig({
    featuresRoot: "..",
    features: [
      "../features/visualization/current_workbench.feature",
      "../features/visualization/current_network_events.feature",
      "../features/visualization/browser_matrix.feature",
      "../features/operations/current_host_tools.feature",
      "../features/operations/current_log_collector.feature",
      "../features/integration/initial_management.feature",
    ],
    steps: [
      "e2e/current.steps.ts",
      "e2e/network-events.steps.ts",
      "e2e/host.steps.ts",
      "e2e/management.steps.ts",
    ],
    outputDir: ".features-gen",
  }),
  reporter: [["list"], ["json", { outputFile: "../reports/bdd-web.json" }]],
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:19123",
    viewport: { width: 1440, height: 900 },
    launchOptions: { args: ["--no-sandbox", "--enable-unsafe-swiftshader"] },
  },
  webServer: {
    command:
      "PYTHONPATH=../vendor/umcp:../mcp-service/src ../.venv/bin/python ../tests/browser_server.py",
    url: "http://127.0.0.1:19123/healthz",
    reuseExistingServer: false,
    timeout: 15000,
  },
});
