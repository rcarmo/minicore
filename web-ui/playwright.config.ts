import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  reporter: "list",
  use: {
    baseURL: process.env.MINICORE_URL ?? "http://127.0.0.1:19000",
    viewport: { width: 1440, height: 900 },
    launchOptions: { args: ["--no-sandbox", "--enable-unsafe-swiftshader"] },
  },
});
