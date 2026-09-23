import { test } from "./host.steps";
import { createBdd } from "playwright-bdd";
import { expect } from "@playwright/test";
import {
  graphSelection,
  webglFallback,
  tabletPolling,
} from "./workbench.checks";
import {
  followPausePaging,
  pollingFallback,
  selectionRace,
} from "./logs.checks";
const { Given, Then } = createBdd(test);
Given("the isolated browser workbench is available", async ({ request }) => {
  expect((await request.get("/healthz")).status()).toBe(200);
});
Then(
  "eight graph labels render and selecting PE1 opens unavailable logs without script errors",
  graphSelection,
);
Then(
  "disabling WebGL still loads the full topology and permits node selection",
  webglFallback,
);
Then(
  "tablet-sized polling preserves P1 selection without horizontal overflow",
  tabletPolling,
);
Then(
  "log follow, pause, new-event notification, paging and node switching preserve context and inert text",
  followPausePaging,
);
Then("new log rows appear by polling when SSE is unavailable", pollingFallback);
Then(
  "late P1 responses never populate the selected P2 inspector",
  selectionRace,
);

Then(
  "orbit, pan, zoom and reset change only the view while all eight nodes remain present",
  async ({ page }) => {
    await (await import("./workbench.checks")).cameraControls({ page });
  },
);
Then(
  "Interfaces and Routing report their unavailable backend without hiding Summary or Logs",
  async ({ page }) => {
    await (await import("./workbench.checks")).unavailableTabs({ page });
  },
);
Then(
  "topology notifications and the 15-second poll fetch authoritative snapshots while preserving selection",
  async ({ page }) => {
    await (await import("./workbench.checks")).topologyReconciliation({ page });
  },
);
Then(
  "schema, node, link and log-page validation reject malformed data rather than rendering invented state",
  async () => {
    const { validateSnapshot } = await import("../src/topology");
    const { validateLogPage } = await import("../src/logs");
    const snapshot = {
      schema_version: "1.0",
      lab_id: "test",
      generation: 1,
      revision: "r1",
      collected_at: "2026-01-01T00:00:00Z",
      nodes: [],
      links: [],
    };
    expect(validateSnapshot(snapshot).revision).toBe("r1");
    for (const data of [
      { ...snapshot, schema_version: "2" },
      { ...snapshot, nodes: [{ id: "p1" }] },
      {
        ...snapshot,
        links: [{ id: "x", source: "p1", target: "p2", state: "unknown" }],
      },
    ])
      expect(() => validateSnapshot(data)).toThrow();
    const logs = {
      node_id: "p1",
      generation: 1,
      status: "ok",
      data: { entries: [], revision: "r1", next_cursor: null },
    };
    expect(validateLogPage(logs, "p1").generation).toBe(1);
    expect(() => validateLogPage(logs, "p2")).toThrow();
    expect(() =>
      validateLogPage(
        { ...logs, data: { ...logs.data, entries: [{ message: "bad" }] } },
        "p1",
      ),
    ).toThrow();
  },
);

Then(
  "the Configuration tab shows declared files, renders selected file text and preserves the selected node",
  async ({ page }) => {
    await page.goto("/#p1");
    await page
      .getByRole("button", { name: "Configuration", exact: true })
      .click();
    await expect(
      page.getByText("Declared baseline — not verified running configuration", {
        exact: true,
      }),
    ).toBeVisible();
    await page.getByRole("button", { name: "frr.conf", exact: true }).click();
    await expect(page.getByLabel("Configuration file contents")).toContainText(
      "router bgp 65000",
    );
    await page.getByRole("button", { name: "daemons", exact: true }).click();
    await expect(page.getByLabel("Configuration file contents")).toContainText(
      "zebra=yes",
    );
    await page
      .locator(".graph-label")
      .filter({ hasText: /^HOST1$/ })
      .click();
    await page
      .getByRole("button", { name: "network.json", exact: true })
      .click();
    await expect(page.getByLabel("Configuration file contents")).toContainText(
      "10.200.8.3",
    );
    await expect(
      page.getByRole("heading", { name: "HOST1", exact: true }),
    ).toBeVisible();
  },
);
Then(
  "configuration markup remains inert and a delayed P1 file never appears under P2",
  async ({ page }) => {
    await page.route(
      /\/api\/v1\/nodes\/(p1|p2)\/config(?:\/frr.conf)?$/,
      async (route) => {
        const path = new URL(route.request().url()).pathname,
          node = path.split("/")[4];
        if (path.endsWith("/config"))
          return route.fulfill({
            json: {
              data: {
                node_id: node,
                source: "declared_baseline",
                files: [{ name: "frr.conf" }],
              },
            },
          });
        if (node === "p1") await new Promise((r) => setTimeout(r, 800));
        await route
          .fulfill({
            json: {
              data: {
                node_id: node,
                name: "frr.conf",
                source: "declared_baseline",
                revision: "test",
                redacted: false,
                content: `${node} <img src=x onerror="window.configExecuted=true">`,
              },
            },
          })
          .catch(() => {});
      },
    );
    await page.goto("/#p1");
    await page
      .getByRole("button", { name: "Configuration", exact: true })
      .click();
    await page.getByRole("button", { name: "frr.conf", exact: true }).click();
    await page.locator(".graph-label").filter({ hasText: /^P2$/ }).click();
    await page.getByRole("button", { name: "frr.conf", exact: true }).click();
    await expect(page.getByLabel("Configuration file contents")).toContainText(
      "p2 <img",
    );
    await page.waitForTimeout(1000);
    await expect(
      page.getByLabel("Configuration file contents"),
    ).not.toContainText("p1");
    expect(await page.locator(".config-content img").count()).toBe(0);
    expect(
      await page.evaluate(() => Boolean((window as any).configExecuted)),
    ).toBe(false);
  },
);
Then(
  "the Routing tab displays a node-scoped evidence response and does not confuse transport errors with missing routes",
  async ({ page }) => {
    await page.route("**/api/v1/nodes/p1/routes", (route) =>
      route.fulfill({
        json: {
          node_id: "p1",
          operation: "get_routes",
          status: "ok",
          error_code: null,
          generation: 1,
          collected_at: "2026-09-23T00:00:00Z",
          duration_ms: 4,
          raw_evidence: "{}",
          data: {
            "10.200.8.0/29": [
              { protocol: "bgp", nexthops: [{ ip: "10.254.0.3" }] },
            ],
          },
        },
      }),
    );
    await page.goto("/#p1");
    await page.getByRole("button", { name: "Routing", exact: true }).click();
    await expect(page.getByLabel("Node routing evidence")).toContainText(
      "10.200.8.0/29",
    );
    await page.locator(".graph-label").filter({ hasText: /^P2$/ }).click();
    await expect(
      page.getByText("Routing evidence unavailable: backend_not_configured", {
        exact: true,
      }),
    ).toBeVisible();
  },
);
Then(
  "a node activity event creates a bounded halo and accessible cue, overlap stays lit, and completion fades without changing selection",
  async ({ page }) => {
    let active = true;
    const data = () => ({
      epoch: "test",
      generation: 1,
      revision: active ? 1 : 2,
      active: active
        ? [
            {
              node_id: "p1",
              request_id: "first",
              expires_at: Date.now() / 1000 + 3,
            },
            {
              node_id: "p1",
              request_id: "second",
              expires_at: Date.now() / 1000 + 3,
            },
          ]
        : [],
      recent: [],
    });
    await page.route("**/api/v1/activity", (r) => r.fulfill({ json: data() }));
    await page.route("**/api/v1/activity/events", (r) =>
      r.fulfill({
        contentType: "text/event-stream",
        body: `retry: 300\nevent: activity.snapshot\ndata: ${JSON.stringify(data())}\n\n`,
      }),
    );
    await page.goto("/#p1");
    const label = page.locator(".graph-label").filter({ hasText: /^P1$/ });
    await expect(label).toHaveAttribute("data-agent-active", "true");
    await expect(label).toHaveAttribute("aria-label", "P1 — Agent access");
    active = false;
    await expect(label).toHaveAttribute("data-agent-active", "false", {
      timeout: 10000,
    });
    await expect(
      page.getByRole("heading", { name: "P1", exact: true }),
    ).toBeVisible();
  },
);
Then(
  "reduced motion uses a steady activity ring and obsolete generations never light a node",
  async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    let generation = 1;
    const data = () => ({
      epoch: "test",
      generation,
      revision: 1,
      active: [
        {
          node_id: "p1",
          request_id: "first",
          expires_at: Date.now() / 1000 + 3,
        },
      ],
      recent: [],
    });
    await page.route("**/api/v1/activity", (r) => r.fulfill({ json: data() }));
    await page.route("**/api/v1/activity/events", (r) =>
      r.fulfill({
        contentType: "text/event-stream",
        body: `retry: 300\nevent: activity.snapshot\ndata: ${JSON.stringify(data())}\n\n`,
      }),
    );
    await page.goto("/#p1");
    const label = page.locator(".graph-label").filter({ hasText: /^P1$/ });
    await expect(label).toHaveAttribute("data-agent-active", "true");
    expect(await label.evaluate((el) => getComputedStyle(el).boxShadow)).toBe(
      "none",
    );
    generation = 0;
    await expect(label).toHaveAttribute("data-agent-active", "false", {
      timeout: 10000,
    });
  },
);
