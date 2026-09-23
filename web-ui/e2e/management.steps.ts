import { expect } from "@playwright/test";
import { createBdd } from "playwright-bdd";
const { Given, When, Then } = createBdd();
Given("the initial management container is ready", async ({ request }) => {
  expect((await request.get("/healthz")).ok()).toBe(true);
});
When("I open the network workbench", async ({ page }) => {
  await page.goto("/");
});
Then("I see eight nodes and nine links", async ({ page }) => {
  await expect(page.getByText("8 nodes / 9 links")).toBeVisible();
  await expect(page.locator(".graph-label")).toHaveCount(8);
});
Then("I can select PE1 and open its log browser", async ({ page }) => {
  await page.locator(".graph-label").filter({ hasText: /^PE1$/ }).click();
  await page.getByRole("button", { name: "Logs", exact: true }).click();
});
Then(
  "the log browser reports that its backend is not configured",
  async ({ page }) => {
    await expect(page.getByRole("status")).toHaveText(
      "Logs unavailable: backend_not_configured",
    );
  },
);
// Session headers live in the scenario's isolated request context, not a process-global variable.
When("an Operator initializes an MCP session", async ({ request }) => {
  const r = await request.post("/mcp", {
    headers: { Accept: "application/json, text/event-stream" },
    data: {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-03-26",
        capabilities: {},
        clientInfo: { name: "minicore-bdd", version: "0.1" },
      },
    },
  });
  expect(r.status()).toBe(200);
  expect((await r.json()).result.protocolVersion).toBe("2025-03-26");
});
const headers = {
  Accept: "application/json, text/event-stream",
  "MCP-Protocol-Version": "2025-03-26",
};
Then(
  "discovery exposes exactly the five diagnostic tools",
  async ({ request }) => {
    const r = await request.post("/mcp", {
      headers,
      data: { jsonrpc: "2.0", id: 2, method: "tools/list" },
    });
    expect(
      (await r.json()).result.tools.map((t: { name: string }) => t.name).sort(),
    ).toEqual([
      "get_interfaces",
      "get_neighbors",
      "get_routes",
      "list_nodes",
      "ping",
    ]);
  },
);
Then("list_nodes returns all eight expected nodes", async ({ request }) => {
  const r = await request.post("/mcp", {
    headers,
    data: {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: "list_nodes" },
    },
  });
  expect((await r.json()).result.structuredContent.data.nodes).toHaveLength(8);
});
Then(
  "get_routes reports backend_not_configured as a tool error",
  async ({ request }) => {
    const r = await request.post("/mcp", {
      headers,
      data: {
        jsonrpc: "2.0",
        id: 4,
        method: "tools/call",
        params: { name: "get_routes", arguments: { node_id: "p1" } },
      },
    });
    const result = (await r.json()).result;
    expect(result.isError).toBe(true);
    expect(result.structuredContent.error_code).toBe("backend_not_configured");
  },
);
Then("reset_lab is denied before any mutation", async ({ request }) => {
  const r = await request.post("/mcp", {
    headers,
    data: {
      jsonrpc: "2.0",
      id: 5,
      method: "tools/call",
      params: {
        name: "reset_lab",
        arguments: { idempotency_key: "bdd-reset-test" },
      },
    },
  });
  expect(r.status()).toBe(403);
});
