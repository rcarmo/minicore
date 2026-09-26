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
      page.getByText("Saved configuration", {
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
      page.getByText("Routing unavailable: Live collector not connected", {
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
Then(
  "an authorised God checkbox reveals source-labelled controller state and unchecking it clears that state without changing node selection",
  async ({ page }) => {
    await page.route("**/api/v1/view", (r) =>
      r.fulfill({ json: { can_god: true } }),
    );
    await page.route("**/api/v1/topology*", async (r) => {
      const data = await (
        await r.fetch({
          url: "http://127.0.0.1:19123/api/v1/topology?view=agent",
        })
      ).json();
      const god = new URL(r.request().url()).searchParams.get("view") === "god";
      await r.fulfill({
        json: {
          ...data,
          view: god ? "god" : "agent",
          ...(god
            ? {
                controller: {
                  state: "active",
                  scenario_id: "test-fault",
                  node_id: "p1",
                },
              }
            : {}),
        },
      });
    });
    await page.goto("/#p1");
    const checkbox = page.getByRole("checkbox", { name: /God mode/ });
    await expect(checkbox).not.toBeChecked();
    await checkbox.check();
    await expect(page.getByLabel("Controller ground truth")).toContainText(
      "test-fault",
    );
    await checkbox.uncheck();
    await expect(page.getByLabel("Controller ground truth")).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "P1", exact: true }),
    ).toBeVisible();
    // Drain SSE-triggered mock fetches before closing their page.
    await page.unrouteAll({ behavior: "wait" });
  },
);
Then(
  "an Operator cannot enable the checkbox and a late God-view response cannot overwrite Agent view",
  async ({ page }) => {
    await page.goto("/#p1");
    await expect(
      page.getByRole("checkbox", { name: /God mode/ }),
    ).toBeDisabled();
    await page.route("**/api/v1/view", (r) =>
      r.fulfill({ json: { can_god: true } }),
    );
    await page.route("**/api/v1/topology*", async (r) => {
      const data = await (
        await r.fetch({
          url: "http://127.0.0.1:19123/api/v1/topology?view=agent",
        })
      ).json();
      const god = new URL(r.request().url()).searchParams.get("view") === "god";
      if (god) await new Promise((resolve) => setTimeout(resolve, 800));
      await r
        .fulfill({
          json: {
            ...data,
            ...(god
              ? {
                  controller: { state: "active", scenario_id: "must-not-leak" },
                }
              : {}),
          },
        })
        .catch(() => {});
    });
    await page.reload();
    const checkbox = page.getByRole("checkbox", { name: /God mode/ });
    await checkbox.check();
    await checkbox.uncheck();
    await page.waitForTimeout(1200);
    await expect(page.getByLabel("Controller ground truth")).toHaveCount(0);
    await expect(checkbox).not.toBeChecked();
  },
);

Then(
  "the workbench can switch AS, OSPF, BGP and prefix layers with source labels and a six-router evidence matrix",
  async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "P1", exact: true }).last().click();
    for (const layer of ["AS", "OSPF", "BGP", "Prefix"]) {
      await page.getByRole("button", { name: layer, exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "P1", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("region", { name: "Routing layers" }),
      ).toContainText("Live");
    }
    await expect(
      page
        .getByRole("table", { name: "Exact prefix evidence" })
        .locator("tbody tr"),
    ).toHaveCount(6);
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).toContainText("not collected");
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).toContainText("Live collector not connected");
  },
);

async function routingFixture(page: import("@playwright/test").Page) {
  const topology = await (await page.request.get("/api/v1/topology")).json();
  return (prefix: string) => ({
    generation: topology.generation,
    status: "ok",
    data: {
      prefix,
      collected: 6,
      expected: 6,
      atomic: false,
      nodes: topology.nodes
        .filter((n: { kind: string }) => n.kind === "router")
        .map((n: { id: string }) => ({
          node_id: n.id,
          generation: topology.generation,
          source: "node_dispatcher",
          collected_at: new Date(Date.now() - 29000).toISOString(),
          error_code: null,
          truncated: false,
          data: {
            prefix,
            bgp: { paths: [] },
            rib: {},
            fib: [],
            advertised: [],
            received: { status: "not_collected" },
            ospf_neighbors: {},
            bgp_peers: {
              ipv4Unicast: {
                peers: {
                  "10.254.0.2": { state: "Established" },
                  "10.254.0.1": { state: "Idle" },
                },
              },
            },
          },
        })),
    },
  });
}
Then(
  "routing evidence becomes stale and BGP endpoint disagreement is not collapsed",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    await page.route("**/api/v1/routing?*", (route) =>
      route.fulfill({ json: fixture("10.200.8.0/29") }),
    );
    await page.goto("/");
    await page.getByRole("button", { name: "BGP", exact: true }).click();
    const row = page
      .getByRole("table", { name: "BGP endpoint observations" })
      .getByRole("row")
      .filter({ hasText: "p1 ↔ p2" });
    await expect(row).toContainText("Established");
    await expect(row).toContainText("Idle");
    await expect(row).toContainText("stale", { timeout: 6000 });
  },
);
Then(
  "a late first-prefix response cannot replace the second prefix evidence",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    await page.route("**/api/v1/routing?*", async (route) => {
      const prefix = new URL(route.request().url()).searchParams.get("prefix")!;
      const result = fixture(prefix);
      if (prefix === "10.200.8.0/29") {
        await new Promise((r) => setTimeout(r, 1000));
        result.status = "late-first-prefix";
      }
      await route.fulfill({ json: result });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Prefix", exact: true }).click();
    await page
      .getByLabel("Prefix", { exact: true })
      .selectOption("10.200.9.0/29");
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).toContainText("ok · 6/6 collected");
    await page.waitForTimeout(1200);
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).not.toContainText("late-first-prefix");
    await expect(page.getByLabel("Prefix", { exact: true })).toHaveValue(
      "10.200.9.0/29",
    );
  },
);

Then(
  "routing comparison shows observed withdrawals but never converts a failed refresh into one",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    let call = 0;
    await page.route("**/api/v1/routing?*", async (route) => {
      call++;
      if (call === 3) {
        await route.fulfill({
          status: 503,
          json: { error_code: "execution_timeout" },
        });
        return;
      }
      const value = fixture("10.200.8.0/29");
      for (const node of value.data.nodes) {
        node.collected_at = new Date().toISOString();
        if (call === 1)
          node.data.bgp = {
            paths: [{ valid: true, bestpath: { overall: true } }],
          };
      }
      await route.fulfill({ json: value });
    });
    await page.goto("/#p1");
    await page.getByRole("button", { name: "Prefix", exact: true }).click();
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).toContainText("ok · 6/6 collected");
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("Waiting for two fresh updates");
    await page
      .getByRole("button", { name: "Collect routing evidence", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("BGP: withdrawn");
    const stamp = await page
      .getByRole("table", { name: "Exact prefix evidence" })
      .locator("tbody th")
      .first()
      .textContent();
    await page
      .getByRole("button", { name: "Collect routing evidence", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("Comparison unavailable");
    await expect(
      page
        .getByRole("table", { name: "Exact prefix evidence" })
        .locator("tbody th")
        .first(),
    ).toHaveText(stamp!);
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).not.toContainText("withdrawn");
    await page
      .getByRole("button", { name: "Collect routing evidence", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("No changes");
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).not.toContainText("withdrawn");
  },
);

Then(
  "a successful automatic poll after a 503 clears the routing error and restores comparison",
  async ({ page }) => {
    await page.clock.install();
    const fixture = await routingFixture(page);
    let call = 0;
    await page.route("**/api/v1/routing?*", async (route) => {
      call++;
      if (call === 2) {
        await route.fulfill({
          status: 503,
          json: { error_code: "execution_timeout" },
        });
        return;
      }
      const value = fixture("10.200.8.0/29");
      for (const node of value.data.nodes) {
        node.collected_at = new Date().toISOString();
        node.data.bgp =
          call === 1
            ? { paths: [{ valid: true, bestpath: { overall: true } }] }
            : { paths: [] };
      }
      await route.fulfill({ json: value });
    });
    await page.goto("/#p1");
    await page.getByRole("button", { name: "Prefix", exact: true }).click();
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("Waiting for two fresh updates");
    await page.clock.fastForward(5000);
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).toContainText("Refresh failed — showing the last update");
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("Comparison unavailable");
    await page.clock.fastForward(5000);
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).not.toContainText("Refresh failed — showing the last update");
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("BGP: withdrawn");
  },
);

Then(
  "a new generation clears earlier routing comparisons without moving node selection",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    const topology = await (await page.request.get("/api/v1/topology")).json();
    let generation = topology.generation;
    await page.route("**/api/v1/topology?*", (r) =>
      r.fulfill({
        json: { ...topology, generation, revision: `gen-${generation}` },
      }),
    );
    await page.route("**/api/v1/routing?*", (r) => {
      const value = fixture("10.200.8.0/29");
      value.generation = generation;
      value.data.nodes.forEach((n: any) => {
        n.generation = generation;
        n.collected_at = new Date().toISOString();
      });
      return r.fulfill({ json: value });
    });
    await page.goto("/#p1");
    await page.getByRole("button", { name: "Prefix", exact: true }).click();
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).toContainText("ok · 6/6 collected");
    await page
      .getByRole("button", { name: "Collect routing evidence", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("No changes");
    generation++;
    await page.evaluate(() =>
      document.dispatchEvent(new Event("visibilitychange")),
    );
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("Waiting for two fresh updates");
    await expect(
      page.getByRole("heading", { name: "P1", exact: true }),
    ).toBeVisible();
  },
);

Then(
  "BGP and OSPF graph labels match the same endpoint facts shown in their tables",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    await page.route("**/api/v1/routing?*", (r) => {
      const value = fixture("10.200.8.0/29");
      value.data.nodes.forEach((n: any) => {
        n.collected_at = new Date().toISOString();
        n.data.ospf_neighbors = {
          "10.254.0.2": [{ ifaceName: "to-p2:10.200.1.2", nbrState: "Full/-" }],
        };
      });
      return r.fulfill({ json: value });
    });
    await page.goto("/#p1");
    for (const layer of ["BGP", "OSPF"]) {
      await page.getByRole("button", { name: layer, exact: true }).click();
      const labels = page.locator(".graph .protocol-label");
      await expect(labels).toHaveCount(0);
      const table = page.getByRole("table", {
        name: `${layer} endpoint observations`,
      });
      await expect(table).toContainText(
        layer === "BGP" ? "Established" : "Full/-",
      );
      for (const title of await page
        .getByLabel("Protocol relationship graph", { exact: true })
        .locator(".protocol-edge title")
        .allTextContents())
        await expect(table).toContainText(title);
    }
    await expect(page.locator(".graph-label")).toHaveCount(8);
  },
);

Then(
  "God annotations never appear in an Agent tab and revocation clears the privileged tab",
  async ({ page, context }) => {
    const topology = await (await page.request.get("/api/v1/topology")).json();
    let revoked = false;
    await context.route("**/api/v1/view", (r) =>
      r.fulfill({ json: { can_god: !revoked } }),
    );
    await context.route("**/api/v1/topology?*", (r) => {
      const god = new URL(r.request().url()).searchParams.get("view") === "god";
      if (god && revoked)
        return r.fulfill({
          status: 403,
          json: { error_code: "authorization_denied" },
        });
      return r.fulfill({
        json: {
          ...topology,
          view: god ? "god" : "agent",
          ...(god
            ? {
                controller: {
                  state: "active",
                  scenario_id: "test-fault",
                  node_id: "p1",
                  interface: "to-p2",
                  verified: true,
                },
              }
            : {}),
        },
      });
    });
    const agent = await context.newPage();
    await page.goto("/");
    await agent.goto("/");
    await page.getByRole("checkbox", { name: /God mode/ }).check();
    await expect(page.getByLabel("Controller ground truth")).toContainText(
      "test-fault",
    );
    await expect(
      agent.getByRole("checkbox", { name: /God mode/ }),
    ).not.toBeChecked();
    await expect(agent.getByLabel("Controller ground truth")).toHaveCount(0);
    revoked = true;
    await page.evaluate(() =>
      document.dispatchEvent(new Event("visibilitychange")),
    );
    await expect(page.getByLabel("Controller ground truth")).toHaveCount(0);
    await expect(
      page.getByRole("checkbox", { name: /God mode/ }),
    ).not.toBeChecked();
    await page.unrouteAll({ behavior: "wait" });
    await agent.close();
  },
);

Then(
  "a {string} routing sample cannot claim an observed withdrawal or healthy session",
  async ({ page }, condition: string) => {
    const fixture = await routingFixture(page);
    let call = 0;
    await page.route("**/api/v1/routing?*", (r) => {
      const v = fixture("10.200.8.0/29");
      v.data.nodes.forEach(
        (n: any) => (n.collected_at = new Date().toISOString()),
      );
      if (++call > 1) {
        if (condition === "partial") {
          v.status = "partial";
          v.data.nodes[0].error_code = "execution_timeout";
          v.data.nodes[0].data = null;
        }
        if (condition === "stale")
          v.data.nodes.forEach(
            (n: any) =>
              (n.collected_at = new Date(Date.now() - 60000).toISOString()),
          );
        if (condition === "truncated") v.data.nodes[0].truncated = true;
        if (condition === "duplicate")
          v.data.nodes[0].node_id = v.data.nodes[1].node_id;
        if (condition === "bad-time")
          v.data.nodes[0].collected_at = "invalid-date";
      }
      return r.fulfill({ json: v });
    });
    await page.goto("/#p1");
    await page.getByRole("button", { name: "Prefix", exact: true }).click();
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).toContainText("ok · 6/6 collected");
    await page
      .getByRole("button", { name: "Collect routing evidence", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).not.toContainText("No changes");
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).not.toContainText("withdrawn");
    await page.getByRole("button", { name: "BGP", exact: true }).click();
    // A failed node must not erase independently collected facts on other nodes.
    await expect(
      page
        .getByRole("table", { name: "BGP endpoint observations" })
        .getByRole("row")
        .filter({ hasText: "p1 ↔ p2" }),
    ).not.toContainText("Established · fresh");
  },
);
Then(
  "keyboard and touch-sized routing controls retain selection without accumulating graph labels",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    await page.route("**/api/v1/routing?*", (r) =>
      r.fulfill({ json: fixture("10.200.8.0/29") }),
    );
    await page.setViewportSize({ width: 820, height: 1180 });
    await page.goto("/#p1");
    for (let cycle = 0; cycle < 4; cycle++)
      for (const name of ["BGP", "OSPF", "AS", "Prefix"]) {
        const button = page.getByRole("button", { name, exact: true });
        await button.focus();
        await page.keyboard.press("Enter");
        await expect(button).toHaveAttribute("aria-pressed", "true");
        await expect(
          page.getByRole("heading", { name: "P1", exact: true }),
        ).toBeVisible();
        await expect(page.locator(".graph-label")).toHaveCount(8);
        await expect(page.locator(".protocol-label")).toHaveCount(0);
        const box = await button.boundingBox();
        expect(box!.height).toBeGreaterThanOrEqual(32);
      }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  },
);

Then(
  "changed peer addresses within a generation clear routing evidence until recollected",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    const topology = await (await page.request.get("/api/v1/topology")).json();
    let changed = false;
    let reads = 0;
    await page.route("**/api/v1/topology?*", (r) =>
      r.fulfill({
        json: {
          ...topology,
          revision: changed ? "changed-peers" : topology.revision,
          peerings: topology.peerings.map((p: any) =>
            changed ? { ...p, target_address: "192.0.2.1" } : p,
          ),
        },
      }),
    );
    await page.route("**/api/v1/routing?*", async (r) => {
      reads++;
      if (changed) await new Promise((resolve) => setTimeout(resolve, 1200));
      // A topology refresh aborts the preceding collection. That intercepted
      // request may already be closed when this deliberate delay expires.
      if (r.request().failure()) return;
      await r.fulfill({ json: fixture("10.200.8.0/29") });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "BGP", exact: true }).click();
    await expect(
      page.getByRole("table", { name: "BGP endpoint observations" }),
    ).toContainText("Established");
    changed = true;
    await page.evaluate(() =>
      document.dispatchEvent(new Event("visibilitychange")),
    );
    await expect.poll(() => reads).toBeGreaterThan(1);
    await expect(
      page.getByRole("table", { name: "BGP endpoint observations" }),
    ).toContainText("not collected");
    await page.getByRole("button", { name: "Pause live routing" }).click();
    await page.waitForTimeout(1400);
    await page.unrouteAll({ behavior: "ignoreErrors" });
  },
);

Then(
  "accessible node controls and routing comparisons work without relying on WebGL",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    await page.route("**/api/v1/routing?*", (r) => {
      const v = fixture("10.200.8.0/29");
      v.data.nodes.forEach(
        (n: any) => (n.collected_at = new Date().toISOString()),
      );
      return r.fulfill({ json: v });
    });
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (
        type: any,
        ...args: any[]
      ) {
        if (type === "webgl2") return null;
        return original.apply(this, [type, ...args] as any);
      } as any;
    });
    await page.setViewportSize({ width: 820, height: 1180 });
    await page.goto("/");
    await expect(page.getByRole("alert")).toContainText("WebGL2 unavailable");
    await page
      .locator(".node-list")
      .getByRole("button", { name: "P1", exact: true })
      .focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("heading", { name: "P1", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Configuration", exact: true })
      .click();
    await page.getByRole("button", { name: "frr.conf", exact: true }).click();
    await expect(page.getByLabel("Configuration file contents")).toContainText(
      "router bgp 65000",
    );
    for (const layer of ["AS", "OSPF", "BGP", "Prefix"]) {
      const button = page.getByRole("button", { name: layer, exact: true });
      await button.focus();
      await page.keyboard.press("Enter");
      await expect(button).toHaveAttribute("aria-pressed", "true");
      await expect(
        page.getByRole("heading", { name: "P1", exact: true }),
      ).toBeVisible();
    }
    await expect(
      page
        .getByRole("table", { name: "Exact prefix evidence" })
        .locator("tbody tr"),
    ).toHaveCount(6);
    await expect(
      page.getByRole("region", { name: "Routing layers" }),
    ).toContainText("ok · 6/6 collected");
    await page
      .getByRole("button", { name: "Collect routing evidence", exact: true })
      .click();
    await expect(
      page.getByRole("region", { name: "Routing comparison" }),
    ).toContainText("No changes");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  },
);

Then(
  "BGP and OSPF keep every node unobscured and show only the selected relationship outside the graph",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    await page.route("**/api/v1/routing?*", (r) =>
      r.fulfill({ json: fixture("10.200.8.0/29") }),
    );
    await page.goto("/#p1");
    for (const width of [1600, 820]) {
      await page.setViewportSize({ width, height: 1100 });
      for (const layer of ["BGP", "OSPF"]) {
        await page.getByRole("button", { name: layer, exact: true }).click();
        await expect(
          page.getByRole("region", { name: "Routing layers" }),
        ).toContainText("6/6 collected");
        await expect(page.locator(".graph .protocol-label")).toHaveCount(0);
        await expect(page.locator(".graph-label")).toHaveCount(8);
        for (const button of await page.locator(".graph-label").all()) {
          await expect(button).toBeVisible();
          const hit = await button.evaluate((el) => {
            const r = el.getBoundingClientRect();
            const over = document.elementFromPoint(
              r.x + r.width / 2,
              r.y + r.height / 2,
            );
            return {
              ok: el.contains(over),
              label: el.textContent,
              over: over?.outerHTML.slice(0, 250),
              rect: { x: r.x, y: r.y, w: r.width, h: r.height },
            };
          });
          expect(hit.ok, JSON.stringify({ width, layer, ...hit })).toBe(true);
        }
        const table = page.getByRole("table", {
          name: `${layer} endpoint observations`,
        });
        await table
          .getByRole("button", { name: "Inspect p1 ↔ p2", exact: true })
          .click();
        const detail = page.getByRole("region", {
          name: "Selected protocol relationship",
        });
        await expect(detail).toContainText("p1 ↔ p2");
        await expect(
          page
            .locator(".graph")
            .getByRole("region", { name: "Selected protocol relationship" }),
        ).toHaveCount(0);
        await page.locator(".graph-label").filter({ hasText: /^P2$/ }).click();
        await expect(
          page.getByRole("heading", { name: "P2", exact: true }),
        ).toBeVisible();
        await page
          .getByRole("button", { name: "Clear relationship selection" })
          .click();
        await expect(detail).toHaveCount(0);
      }
    }
  },
);

Then(
  "the main 3D topology stays readable while floating diagnostics contain 2D graphs and scrollable tables",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    await page.route("**/api/v1/routing?*", (r) =>
      r.fulfill({ json: fixture("10.200.8.0/29") }),
    );
    await page.goto("/#p1");
    await expect(
      page.getByLabel("Interactive network topology", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Topology dimension" }),
    ).toHaveCount(0);
    await expect(page.locator(".graph svg")).toHaveCount(0);
    await expect(page.locator(".graph-label")).toHaveCount(8);
    await page.getByRole("button", { name: "BGP", exact: true }).click();
    const panel = page.getByRole("region", {
      name: "Routing diagnostics",
      exact: true,
    });
    await expect(panel).toBeVisible();
    await expect(
      panel.getByLabel("Protocol relationship graph", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("table", { name: "BGP endpoint observations" }),
    ).toBeVisible();
    expect(
      await panel
        .locator(".floating-body")
        .evaluate((el) => getComputedStyle(el).overflowY),
    ).toBe("auto");
    expect(
      await panel.evaluate((el) =>
        parseFloat(getComputedStyle(el).borderRadius),
      ),
    ).toBeGreaterThanOrEqual(12);
    const button = page.getByRole("button", { name: "BGP", exact: true });
    expect(
      await button.evaluate((el) =>
        parseFloat(getComputedStyle(el).borderRadius),
      ),
    ).toBeGreaterThanOrEqual(10);
    const before = (await panel.boundingBox())!;
    expect(before.height).toBeLessThan(900 * 0.65);
    expect(before.width).toBeLessThan(1440 * 0.65);
    const handle = panel.getByRole("button", {
      name: "Move Routing diagnostics",
    });
    await handle.focus();
    await page.keyboard.press("ArrowLeft");
    await expect
      .poll(async () => Math.round((await panel.boundingBox())!.x))
      .toBeLessThan(Math.round(before.x));
    const grab = (await handle.boundingBox())!;
    await page.mouse.move(grab.x + 20, grab.y + 20);
    await page.mouse.down();
    await page.mouse.move(grab.x - 40, grab.y - 20, { steps: 5 });
    await page.mouse.up();
    await expect
      .poll(async () => Math.round((await panel.boundingBox())!.x))
      .toBeLessThan(Math.round(before.x) - 20);
    await panel
      .getByRole("button", { name: "Minimize Routing diagnostics" })
      .click();
    await expect(panel.locator(".floating-body")).toBeHidden();
    await panel
      .getByRole("button", { name: "Restore Routing diagnostics" })
      .click();
    await expect(panel.locator(".floating-body")).toBeVisible();
    await page.setViewportSize({ width: 820, height: 1180 });
    const box = (await panel.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(820);
    expect(box.height).toBeLessThan(1180 * 0.6);
    await expect(page.locator(".graph-label")).toHaveCount(8);
  },
);

Then(
  "God can arm lightning or dice click one topology target and return to Inspect while Operator cannot arm either",
  async ({ page }) => {
    const topology = await (await page.request.get("/api/v1/topology")).json();
    let state = "baseline";
    const commands: any[] = [];
    await page.route("**/api/v1/view", (r) =>
      r.fulfill({ json: { can_god: true, fault_control: true } }),
    );
    await page.route("**/api/v1/topology?*", (r) =>
      r.fulfill({
        json: {
          ...topology,
          controller: { state, verified: true },
          view: new URL(r.request().url()).searchParams.get("view"),
        },
      }),
    );
    await page.route("**/api/v1/faults/*", (r) => {
      commands.push({
        body: r.request().postDataJSON(),
        headers: r.request().headers(),
        url: r.request().url(),
      });
      state = r.request().url().endsWith("/reset") ? "baseline" : "active";
      return r.fulfill({
        json: { error_code: null, data: { state, verified: true } },
      });
    });
    await page.goto("/#p1");
    await expect(
      page.getByRole("button", { name: "Lightning — kill target" }),
    ).toHaveCount(0);
    await page.getByRole("checkbox", { name: /God mode/ }).check();
    await page.getByRole("button", { name: "Lightning — kill target" }).click();
    await expect(
      page.getByRole("status", { name: "Fault mode" }),
    ).toContainText("Click a node to stop its container");
    await page.locator(".graph-label").filter({ hasText: /^PE1$/ }).click();
    await expect.poll(() => commands.length).toBe(1);
    expect(commands[0].body).toMatchObject({
      mode: "zap",
      target_type: "node",
      target_id: "pe1",
    });
    expect(commands[0].headers["x-minicore-intent"]).toBe("fault-control");
    await expect(
      page.getByRole("button", { name: "Inspect", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Restore lab" }).click();
    await expect.poll(() => commands.length).toBe(2);
    await page.getByRole("button", { name: "Lightning — kill target" }).click();
    await page.getByRole("button", { name: "Link p1-p2", exact: true }).click();
    await expect.poll(() => commands.length).toBe(3);
    expect(commands[2].body).toMatchObject({
      mode: "zap",
      target_type: "link",
      target_id: "p1-p2",
    });
    await page.getByRole("button", { name: "Restore lab" }).click();
    await expect.poll(() => commands.length).toBe(4);
    await page
      .getByRole("button", { name: "Dice — random corruption" })
      .click();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("button", { name: "Inspect", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await page
      .getByRole("button", { name: "Dice — random corruption" })
      .click();
    await page.locator(".graph-label").filter({ hasText: /^CE1$/ }).click();
    await expect.poll(() => commands.length).toBe(5);
    expect(commands[4].body).toMatchObject({
      mode: "dice",
      target_type: "node",
      target_id: "ce1",
    });
    await page.getByRole("checkbox", { name: /God mode/ }).uncheck();
    await expect(
      page.getByRole("button", { name: "Lightning — kill target" }),
    ).toHaveCount(0);
    await page.unrouteAll({ behavior: "wait" });
  },
);

Then(
  "selected node interfaces and peer states update live with specific collection errors",
  async ({ page }) => {
    let calls = 0;
    await page.route("**/api/v1/nodes/p1/observations", (r) => {
      const up = ++calls === 1,
        generation = 1;
      const source = (data: any, error_code: string | null = null) => ({
        node_id: "p1",
        generation,
        collected_at: new Date().toISOString(),
        source: "node_dispatcher",
        status: error_code ? "unavailable" : "ok",
        data,
        error_code,
      });
      return r.fulfill({
        json: {
          node_id: "p1",
          generation,
          data: {
            interfaces: source([
              {
                ifname: "to-p2",
                operstate: up ? "UP" : "DOWN",
                flags: up ? ["UP"] : [],
                addr_info: [{ local: "10.200.1.2", prefixlen: 29 }],
              },
            ]),
            bgp: source({
              ipv4Unicast: {
                peers: { "10.254.0.2": { state: up ? "Established" : "Idle" } },
              },
            }),
            ospf: source(null, "execution_timeout"),
          },
        },
      });
    });
    await page.goto("/#p1");
    await expect(
      page.getByRole("region", { name: "Live node observations" }),
    ).toContainText("Established");
    await expect(
      page.getByRole("region", { name: "Live node observations" }),
    ).toContainText("Collection timed out");
    await page.getByRole("button", { name: "Interfaces", exact: true }).click();
    const interfaces = page.getByRole("table", { name: "Live interfaces" });
    await expect(interfaces).toContainText("10.200.1.2/29");
    await expect(interfaces).toContainText("DOWN", { timeout: 12000 });
    await expect(
      page.getByRole("heading", { name: "P1", exact: true }),
    ).toBeVisible();
  },
);
Then(
  "the routing panel refreshes evidence without manual collection and pauses when minimized",
  async ({ page }) => {
    const fixture = await routingFixture(page);
    let calls = 0;
    await page.route("**/api/v1/routing?*", (r) => {
      calls++;
      return r.fulfill({ json: fixture("10.200.8.0/29") });
    });
    await page.goto("/#p1");
    await page.getByRole("button", { name: "BGP", exact: true }).click();
    await expect.poll(() => calls, { timeout: 12000 }).toBeGreaterThan(1);
    await page
      .getByRole("button", { name: "Minimize Routing diagnostics" })
      .click();
    await page.waitForTimeout(300);
    const paused = calls;
    await page.waitForTimeout(5500);
    expect(calls).toBe(paused);
    await page
      .getByRole("button", { name: "Restore Routing diagnostics" })
      .click();
    await expect.poll(() => calls).toBeGreaterThan(paused);
  },
);

Then(
  "the inspectors use plain status labels and keep source details collapsed",
  async ({ page }) => {
    await page.goto("/#p1");
    await page
      .getByRole("button", { name: "Configuration", exact: true })
      .click();
    await expect(
      page.getByText("Saved configuration", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Live running configuration has not been collected.", {
        exact: true,
      }),
    ).toBeHidden();
    for (const layer of ["AS", "OSPF", "BGP", "Prefix"]) {
      await page.getByRole("button", { name: layer, exact: true }).click();
      const text = await page.locator("body").innerText();
      expect(text).not.toMatch(
        /does not prove|do not prove|not atomic|not a fresh source|does not imply|not withdrawal|ground truth|declared|scope|≠/i,
      );
    }
    await page.getByRole("button", { name: "Logs", exact: true }).click();
    await expect(
      page.getByRole("region", { name: "Logs for p1" }),
    ).toContainText("Live collector not connected");
    await expect(
      page.getByRole("region", { name: "Logs for p1" }),
    ).not.toContainText("backend_not_configured");
  },
);

Then(
  "the header replaces generation with God mode and keeps all controls inline with accessible touch targets",
  async ({ page }) => {
    const topology = await (await page.request.get("/api/v1/topology")).json();
    let mutations = 0;
    await page.route("**/api/v1/view", (r) =>
      r.fulfill({ json: { can_god: true, fault_control: true } }),
    );
    await page.route("**/api/v1/topology?*", (r) =>
      r.fulfill({
        json: {
          ...topology,
          view: new URL(r.request().url()).searchParams.get("view"),
          controller: { state: "baseline", verified: true },
        },
      }),
    );
    await page.route("**/api/v1/faults/*", (r) => {
      mutations++;
      return r.fulfill({
        json: { error_code: null, data: { state: "baseline", verified: true } },
      });
    });
    await page.goto("/#p1");
    const header = page.locator("header");
    await expect(
      header.getByRole("checkbox", { name: "God mode", exact: true }),
    ).toBeVisible();
    await expect(header).not.toContainText("Generation");
    await expect(
      header.getByRole("navigation", { name: "Network layers" }),
    ).toBeVisible();
    await header
      .getByRole("checkbox", { name: "God mode", exact: true })
      .check();
    await expect(
      header.getByRole("button", { name: "Lightning — kill target" }),
    ).toBeVisible();
    await expect(
      header.getByRole("button", { name: "Reset view", exact: true }),
    ).toBeVisible();
    const layers = header.getByRole("navigation", { name: "Network layers" });
    await layers.getByRole("button", { name: "Physical", exact: true }).focus();
    await page.keyboard.press("ArrowRight");
    await expect(
      layers.getByRole("button", { name: "AS", exact: true }),
    ).toBeFocused();
    await expect(
      layers.getByRole("button", { name: "Physical", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await page.keyboard.press("Enter");
    await expect(
      layers.getByRole("button", { name: "AS", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    for (const width of [1600, 820, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      const row = await header.boundingBox();
      expect(row!.height).toBeLessThanOrEqual(84);
      const controls = [
        header
          .getByRole("checkbox", { name: "God mode", exact: true })
          .locator(".."),
        layers.getByRole("button", { name: "BGP", exact: true }),
        header.getByRole("button", { name: "Lightning — kill target" }),
        header.getByRole("button", { name: "Restore lab" }),
      ];
      const boxes = [];
      for (const control of controls) {
        const box = (await control.boundingBox())!;
        expect(box.height).toBeGreaterThanOrEqual(44);
        expect(box.width).toBeGreaterThanOrEqual(44);
        expect(
          await control.evaluate((el) =>
            parseFloat(getComputedStyle(el).borderRadius),
          ),
        ).toBeGreaterThanOrEqual(8);
        boxes.push(box);
      }
      expect(
        Math.max(...boxes.map((b) => b.y)) - Math.min(...boxes.map((b) => b.y)),
      ).toBeLessThanOrEqual(4);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await header
        .getByRole("button", { name: "Lightning — kill target" })
        .focus();
      await page.keyboard.press("ArrowRight");
      await expect(
        header.getByRole("button", { name: "Dice — random corruption" }),
      ).toBeFocused();
      expect(mutations).toBe(0);
    }
    await header
      .getByRole("checkbox", { name: "God mode", exact: true })
      .uncheck();
    await expect(
      header.getByRole("button", { name: "Lightning — kill target" }),
    ).toHaveCount(0);
    await page.unrouteAll({ behavior: "wait" });
  },
);

Then(
  "log paging stays actionable during refresh and cancels the live request",
  async ({ page }) => {
    let calls = 0;
    let release: () => void = () => {};
    let waiting = false;
    const pause = new Promise<void>((resolve) => (release = resolve));
    const sample = (older: boolean) => ({
      node_id: "p1",
      generation: 1,
      status: "ok",
      error_code: null,
      collected_at: new Date().toISOString(),
      truncated: false,
      data: {
        entries: [
          {
            id: older ? "older" : "latest",
            timestamp: new Date().toISOString(),
            source: "container",
            severity: "info",
            message: older ? "older saved line" : "live latest line",
            truncated: false,
          },
        ],
        revision: older ? "0" : "1",
        next_cursor: older ? null : "older",
        source: "container",
        window_start: new Date().toISOString(),
        window_end: new Date().toISOString(),
        retained_count: 2,
      },
    });
    await page.route("**/api/v1/nodes/p1/logs/events", (r) =>
      r.fulfill({ status: 503, body: "" }),
    );
    await page.route(/\/api\/v1\/nodes\/p1\/logs(?:\?.*)?$/, async (r) => {
      const older = new URL(r.request().url()).searchParams.has("cursor");
      if (!older && ++calls === 2) {
        waiting = true;
        await pause;
        if (r.request().failure()) return;
      }
      await r.fulfill({ json: sample(older) });
    });
    await page.goto("/#p1");
    await page.getByRole("button", { name: "Logs", exact: true }).click();
    await expect(page.getByLabel("Node log entries")).toContainText(
      "live latest line",
    );
    await page.getByRole("button", { name: "Latest", exact: true }).click();
    await expect.poll(() => waiting).toBe(true);
    try {
      await expect(
        page.getByRole("button", { name: "Older", exact: true }),
      ).toBeEnabled();
      await page.getByRole("button", { name: "Older", exact: true }).click();
      await expect(page.getByLabel("Node log entries")).toContainText(
        "older saved line",
      );
      await expect(
        page.getByRole("button", { name: "Follow latest", exact: true }),
      ).toBeVisible();
    } finally {
      release();
      await page.unrouteAll({ behavior: "ignoreErrors" });
    }
  },
);

Then(
  "a successful reset advances generation and enables Inspect without requiring visible status text",
  async ({ page }) => {
    const topology = await (await page.request.get("/api/v1/topology")).json();
    let generation = topology.generation;
    let state = "active";
    let resets = 0;
    await page.route("**/api/v1/view", (r) =>
      r.fulfill({ json: { can_god: true, fault_control: true } }),
    );
    await page.route("**/api/v1/topology?*", (r) =>
      r.fulfill({
        json: {
          ...topology,
          generation,
          revision: `reset-${generation}`,
          controller: { state, verified: true },
          view: new URL(r.request().url()).searchParams.get("view"),
        },
      }),
    );
    await page.route("**/api/v1/faults/reset", (r) => {
      resets++;
      generation++;
      state = "baseline";
      return r.fulfill({
        json: { error_code: null, data: { state, verified: true, generation } },
      });
    });
    await page.goto("/#p1");
    await page.getByRole("checkbox", { name: /God mode/ }).check();
    await expect(page.getByLabel("Controller ground truth")).toContainText(
      "active",
    );
    await page.getByRole("button", { name: "Restore lab" }).click();
    await expect(page.getByLabel("Controller ground truth")).toContainText(
      "baseline",
    );
    await expect(
      page.getByRole("button", { name: "Restore lab" }),
    ).toBeEnabled();
    await expect(
      page.getByRole("button", { name: "Inspect", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(resets).toBe(1);
    expect(generation).toBe(topology.generation + 1);
    await page.unrouteAll({ behavior: "wait" });
  },
);
