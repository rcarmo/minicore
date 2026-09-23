import { defineConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";
export default defineConfig({
  testDir: defineBddConfig({
    featuresRoot: "..",
    features: "../features/integration/live_node_logs.feature",
    steps: "e2e/live-logs.steps.ts",
    outputDir: ".features-logs-gen",
  }),
  reporter: "list",
  use: {
    baseURL: process.env.MINICORE_URL ?? "http://127.0.0.1:19000",
    viewport: { width: 1440, height: 900 },
    launchOptions: { args: ["--no-sandbox", "--enable-unsafe-swiftshader"] },
  },
});
