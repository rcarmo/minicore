import { test } from "@playwright/test";
import { expect } from "@playwright/test";
import { createBdd } from "playwright-bdd";
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const uiRoot = join(here, "..");
const { When, Then } = createBdd();

async function run(args: string[]) {
  const child = spawn(args[0]!, args.slice(1), { cwd: uiRoot });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => (stdout += chunk));
  child.stderr.on("data", (chunk) => (stderr += chunk));
  const code = await new Promise<number>((resolve, reject) => {
    child.on("error", reject);
    child.on("close", (value) => resolve(value ?? 1));
  });
  return { code, stdout, stderr, text: `${stdout}${stderr}` };
}

When("the isolated network events model tests are run", async () => {
  const result = await run(["bun", "test", "src/network-events-model.test.ts"]);
  expect(result.code, result.text).toBe(0);
});

Then("the isolated network events model contract passes", async () => {
  const result = await run(["bun", "test", "src/network-events-model.test.ts"]);
  expect(result.code, result.text).toBe(0);
  expect(result.text).toContain("network events model");
});

When("the isolated network events modules are loaded", async () => {
  const result = await run([
    "bun",
    "-e",
    [
      'const panel = await import("./src/network-events.tsx");',
      'const model = await import("./src/network-events-model.ts");',
      'if (typeof panel.NetworkEvents !== "function") throw new Error("missing NetworkEvents export");',
      'if (typeof model.validateObserverEnvelope !== "function") throw new Error("missing validateObserverEnvelope export");',
      'console.log("exports-ok")',
    ].join(" "),
  ]);
  expect(result.code, result.text).toBe(0);
  expect(result.text).toContain("exports-ok");
});

Then("the standalone NetworkEvents panel export is available", async () => {
  const result = await run([
    "bun",
    "-e",
    'const panel = await import("./src/network-events.tsx"); console.log(typeof panel.NetworkEvents);',
  ]);
  expect(result.code, result.text).toBe(0);
  expect(result.text).toContain("function");
});

Then(
  "multi-sample history retains route changes and counts each interface direction once",
  async () => {
    const result = await run([
      "bun",
      "test",
      "src/network-events-model.test.ts",
      "--test-name-pattern",
      "regression: seconds",
    ]);
    expect(result.code, result.text).toBe(0);
  },
);
Then(
  "oversized lifetimes invalid source enums and conflicting identities are rejected",
  async () => {
    const result = await run([
      "bun",
      "test",
      "src/network-events-model.test.ts",
      "--test-name-pattern",
      "regression: reject",
    ]);
    expect(result.code, result.text).toBe(0);
  },
);
Then(
  "truncated failed and reset-counter samples suppress unsafe comparisons",
  async () => {
    const result = await run([
      "bun",
      "test",
      "src/network-events-model.test.ts",
      "--test-name-pattern",
      "regression: truncated",
    ]);
    expect(result.code, result.text).toBe(0);
  },
);

async function observerFixture(page: import("@playwright/test").Page) {
  const topology = await (await page.request.get("/api/v1/topology")).json();
  return (scope: string, data: unknown, remaining = 55000) => ({
    lab_id: topology.lab_id,
    generation: topology.generation,
    observer_epoch: "observer-test",
    scope,
    window_seconds: 60,
    source_health: "ok",
    missed_updates: 0,
    truncated: false,
    omitted: 0,
    records: [
      {
        scope,
        incarnation: "source-test",
        acquired_monotonic: 123,
        sampled_at: new Date().toISOString(),
        remaining_ms: remaining,
        data,
      },
    ],
  });
}
Then(
  "the network events panel scopes rows highlights a node and never mutates the lab",
  async ({ page }) => {
    const fixture = await observerFixture(page);
    let mutations = 0;
    await page.route("**/api/v1/observer?*", (r) => {
      const u = new URL(r.request().url());
      const kind = u.searchParams.get("kind");
      return r.fulfill({
        json: fixture(
          `node:p1:${kind}`,
          kind === "igmp"
            ? {
                version: 2,
                message_type: "report_v2",
                group: "239.1.1.1",
                reporter: "10.200.8.2",
                querier: null,
                sources: [],
                records: [],
                node_id: "p1",
                interface: "to-p2",
              }
            : {
                peers: [
                  {
                    protocol: "bgp",
                    address: "10.254.0.2",
                    state: "Established",
                  },
                ],
                routes: [],
              },
        ),
      });
    });
    await page.route("**/api/v1/faults/*", (r) => {
      mutations++;
      return r.abort();
    });
    await page.goto("/#p1");
    await page
      .getByRole("button", { name: "Network events", exact: true })
      .click();
    const panel = page.getByRole("region", {
      name: "Network events",
      exact: true,
    });
    await expect(panel).toContainText("Peer Established");
    await panel.getByRole("button", { name: "IGMP", exact: true }).click();
    await expect(panel).toContainText("239.1.1.1");
    await panel
      .getByRole("button", { name: /Inspect/ })
      .first()
      .click();
    await expect(
      page.getByRole("heading", { name: "P1", exact: true }),
    ).toBeVisible();
    expect(mutations).toBe(0);
    await page.getByRole("button", { name: "Close network events" }).click();
    await expect(panel).toHaveCount(0);
  },
);
Then(
  "an expired event disappears while paused and failed refreshes cannot restore it",
  async ({ page }) => {
    const fixture = await observerFixture(page);
    let calls = 0;
    await page.route("**/api/v1/observer?*", (r) =>
      ++calls === 1
        ? r.fulfill({
            json: fixture(
              "node:p1:routing",
              {
                peers: [
                  { protocol: "bgp", address: "10.254.0.2", state: "Idle" },
                ],
                routes: [],
              },
              1800,
            ),
          })
        : r.fulfill({ status: 503, json: { error_code: "collection_failed" } }),
    );
    await page.goto("/#p1");
    await page
      .getByRole("button", { name: "Network events", exact: true })
      .click();
    const panel = page.getByRole("region", {
      name: "Network events",
      exact: true,
    });
    await expect(panel).toContainText("Peer Idle");
    await panel.getByRole("button", { name: "Pause", exact: true }).click();
    await expect(panel).not.toContainText("Peer Idle", { timeout: 6000 });
    await expect(panel).toContainText("Observer unavailable");
    expect(await page.evaluate(() => localStorage.length)).toBe(0);
  },
);
Then(
  "only the newly selected link records appear after a delayed node response",
  async ({ page }) => {
    const fixture = await observerFixture(page);
    await page.route("**/api/v1/observer?*", async (r) => {
      const u = new URL(r.request().url());
      if (u.searchParams.get("scope") === "node") {
        await new Promise((done) => setTimeout(done, 1000));
        if (r.request().failure()) return;
        return r.fulfill({
          json: fixture("node:p1:routing", {
            peers: [{ protocol: "bgp", address: "10.254.0.2", state: "Idle" }],
            routes: [],
          }),
        });
      }
      return r.fulfill({
        json: fixture("link:p1-p2:interfaces", {
          interfaces: [
            {
              node_id: "p1",
              interface: "to-p2",
              state: "UP",
              tx_packets: 4,
              rx_packets: 3,
              tx_bytes: 40,
              rx_bytes: 30,
              tx_errors: 0,
              rx_errors: 0,
              tx_drops: 0,
              rx_drops: 0,
            },
          ],
        }),
      });
    });
    await page.goto("/#p1");
    await page
      .getByRole("button", { name: "Network events", exact: true })
      .click();
    const panel = page.getByRole("region", {
      name: "Network events",
      exact: true,
    });
    await panel.getByLabel("Network event scope").selectOption("link:p1-p2");
    await expect(panel).toContainText("Interface UP");
    await page.waitForTimeout(1200);
    await expect(panel).not.toContainText("Peer Idle");
    await page.getByRole("button", { name: "Close network events" }).click();
  },
);
Then(
  "interleaved endpoint samples produce both directional link rates",
  async () => {
    const result = await run([
      "bun",
      "test",
      "src/network-events-model.test.ts",
      "--test-name-pattern",
      "regression: interleaved",
    ]);
    expect(result.code, result.text).toBe(0);
  },
);
Then(
  "a repeating observer response with the same acquisition expires even while fetches succeed",
  async ({ page }) => {
    const fixture = await observerFixture(page);
    const fixed = fixture(
      "node:p1:routing",
      {
        peers: [{ protocol: "bgp", address: "10.254.0.2", state: "Idle" }],
        routes: [],
      },
      1600,
    );
    let count = 0;
    await page.route("**/api/v1/observer?*", (r) => {
      count++;
      return r.fulfill({ json: fixed });
    });
    await page.goto("/#p1");
    await page
      .getByRole("button", { name: "Network events", exact: true })
      .click();
    const panel = page.getByRole("region", {
      name: "Network events",
      exact: true,
    });
    await expect(panel).toContainText("Peer Idle");
    await page.waitForTimeout(3500);
    await expect(panel).not.toContainText("Peer Idle");
    expect(count).toBeGreaterThan(1);
  },
);
Then(
  "two rows with the same source acquisition cannot hide behind different display timestamps",
  async () => {
    const result = await run([
      "bun",
      "test",
      "src/network-events-model.test.ts",
      "--test-name-pattern",
      "regression: conflicting",
    ]);
    expect(result.code, result.text).toBe(0);
  },
);
Then(
  "a partial link response names the failed endpoint with a plain status message",
  async ({ page }) => {
    const fixture = await observerFixture(page);
    await page.route("**/api/v1/observer?*", (r) => {
      const data = fixture("link:p1-p2:interfaces", { interfaces: [] });
      data.source_health = "collection_timeout";
      data.truncated = true;
      return r.fulfill({
        json: {
          ...data,
          records: [],
          sources: { p1: "ok", p2: "collection_timeout" },
        },
      });
    });
    await page.goto("/#p1");
    await page
      .getByRole("button", { name: "Network events", exact: true })
      .click();
    const panel = page.getByRole("region", {
      name: "Network events",
      exact: true,
    });
    await panel.getByLabel("Network event scope").selectOption("link:p1-p2");
    await expect(panel).toContainText("p2: Collection timed out");
    await expect(panel).not.toContainText("source_health=");
  },
);
Then(
  "a partial link keeps matching healthy source rates and labels the failed source",
  async () => {
    const result = await run([
      "bun",
      "test",
      "src/network-events-model.test.ts",
      "--test-name-pattern",
      "regression: partial link",
    ]);
    expect(result.code, result.text).toBe(0);
  },
);
