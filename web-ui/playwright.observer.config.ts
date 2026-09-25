import base from "./playwright.bdd.config";
import { defineConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";

export default defineConfig({
  ...base,
  testDir: defineBddConfig({
    featuresRoot: "..",
    features: "../features/visualization/current_network_events.feature",
    steps: "e2e/network-events.steps.ts",
    outputDir: ".features-observer-gen",
  }),
  reporter: "list",
  workers: 1,
  use: {
    ...base.use,
    viewport: { width: 1280, height: 800 },
    launchOptions: { args: ["--no-sandbox", "--enable-unsafe-swiftshader"] },
  },
});
