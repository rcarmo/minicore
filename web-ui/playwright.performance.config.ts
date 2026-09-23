import { defineConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";
const testDir = defineBddConfig({
  featuresRoot: "../features",
  features: ["../features/operations/live_performance.feature"],
  steps: ["e2e/performance.steps.ts"],
  outputDir: ".features-performance",
});
export default defineConfig({
  testDir,
  timeout: 120000,
  workers: 1,
  reporter: [
    ["list"],
    ["json", { outputFile: "../reports/performance-acceptance.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:19000",
    viewport: { width: 1440, height: 1000 },
    launchOptions: { args: ["--no-sandbox", "--enable-unsafe-swiftshader"] },
  },
});
