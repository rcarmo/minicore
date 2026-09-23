import { defineConfig } from "@playwright/test";
import base from "./playwright.bdd.config";
export default defineConfig({
  ...base,
  testMatch: "**/browser_matrix.feature.spec.js",
  reporter: [
    ["list"],
    ["json", { outputFile: "../reports/browser-matrix.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:19123",
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        launchOptions: {
          args: ["--no-sandbox", "--enable-unsafe-swiftshader"],
        },
      },
    },
    {
      name: "firefox",
      use: {
        browserName: "firefox",
        launchOptions: { firefoxUserPrefs: { "webgl.force-enabled": true } },
      },
    },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
});
