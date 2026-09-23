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
