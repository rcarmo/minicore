import { defineConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";
export default defineConfig({
  testDir: defineBddConfig({
    featuresRoot: "..",
    features: "../features/operations/node_boot.feature",
    steps: "e2e/node-boot.steps.ts",
    outputDir: ".features-boot-gen",
  }),
  timeout: 180000,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:19000",
    viewport: { width: 1440, height: 900 },
    launchOptions: { args: ["--no-sandbox", "--enable-unsafe-swiftshader"] },
  },
});
