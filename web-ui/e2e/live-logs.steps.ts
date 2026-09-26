import { expect } from "@playwright/test";
import { createBdd } from "playwright-bdd";
const { Given, When, Then } = createBdd();
Given(
  "p1 exists and the host log collector has recently sampled its output",
  async ({ request }) => {
    const response = await request.get("/api/v1/nodes/p1/logs?limit=500");
    expect(response.status()).toBe(200);
    const page = await response.json();
    expect(page.error_code).toBeNull();
    expect(page.data.entries.length).toBeGreaterThan(0);
  },
);
When("I open p1 in the network workbench and select Logs", async ({ page }) => {
  await page.goto("/#p1");
  await page.getByRole("button", { name: "Logs", exact: true }).click();
});
Then(
  "real container-source entries are displayed",
  async ({ page, request }) => {
    await expect(page.locator(".log-entry").first()).toBeVisible();
    const response = await request.get("/api/v1/nodes/p1/logs");
    expect(response.status()).toBe(200);
    const result = await response.json();
    expect(result.data.source).toBe("container");
    expect(result.data.entries.length).toBeGreaterThan(0);
    expect(
      result.data.entries.every(
        (entry: { source: string }) => entry.source === "container",
      ),
    ).toBe(true);
  },
);
Then(
  "successful startup events are visible without capability failures",
  async ({ page }) => {
    await page.getByLabel("Severity").selectOption("all");
    await expect(page.getByLabel("Node log entries")).not.toContainText(
      "cap_set_proc failed",
    );
    await expect(page.getByLabel("Node log entries")).toContainText(
      "all daemons up",
    );
    await page.screenshot({
      path: "../docs/evidence/node-logs.png",
      fullPage: true,
    });
  },
);
Then("pausing and following preserves the selected node", async ({ page }) => {
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "P1", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Follow latest", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "P1", exact: true }),
  ).toBeVisible();
});
