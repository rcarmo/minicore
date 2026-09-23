import { createBdd, test as base } from "playwright-bdd";
import { expect, type BrowserContext, type Page } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
const root = resolve("..");
async function call(role: string, tool: string, args: object = {}) {
  const child = spawn(
    root + "/.venv/bin/python",
    [root + "/tests/mcp_harness/tool_cli.py", role, tool, JSON.stringify(args)],
    { cwd: root, timeout: 130000 },
  );
  let out = "",
    err = "";
  child.stdout.on("data", (b) => (out += b));
  child.stderr.on("data", (b) => (err += b));
  const code = await new Promise<number | null>((resolve, reject) => {
    child.on("error", reject);
    child.on("close", resolve);
  });
  expect(code, err).toBe(0);
  const value = JSON.parse(out);
  expect(value.isError, JSON.stringify(value)).toBe(false);
  return value.evidence;
}
type State = {
  god: Page;
  operator: Page;
  contexts: BrowserContext[];
  scenario?: string;
  generation?: number;
  reset?: number;
};
export const test = base.extend<{ state: State }>({
  state: async ({ browser }, use) => {
    const tokens = JSON.parse(
      await readFile(root + "/secrets/http/mcp-tokens.json", "utf8"),
    );
    const contexts = await Promise.all(
      ["god", "operator"].map((username) =>
        browser.newContext({
          httpCredentials: { username, password: tokens[username] },
          // Private loopback does not challenge anonymous callers; send the existing
          // role credential explicitly, just as an authenticated browser would.
          extraHTTPHeaders: {
            Authorization:
              "Basic " +
              Buffer.from(`${username}:${tokens[username]}`).toString("base64"),
          },
          baseURL: "http://127.0.0.1:19000",
          viewport: { width: 1440, height: 1000 },
        }),
      ),
    );
    const state = {
      god: await contexts[0].newPage(),
      operator: await contexts[1].newPage(),
      contexts,
    };
    try {
      await use(state);
    } finally {
      const status = await call("god", "get_fault_state");
      if (status.data.state !== "baseline")
        await call("god", "reset_lab", {
          idempotency_key: crypto.randomUUID(),
        });
      await Promise.all(contexts.map((c) => c.close()));
    }
  },
});
const { Given, When, Then } = createBdd(test);
Given(
  "separate authenticated God and Operator browser contexts on the local lab",
  async ({ state }) => {
    const status = await call("god", "get_fault_state");
    expect(status.data.state).toBe("baseline");
    state.generation = status.generation;
    await state.god.goto("/#p1");
    await state.operator.goto("/#p1");
    await expect(
      state.operator.getByRole("checkbox", { name: /God mode/ }),
    ).toBeDisabled();
    await state.god.getByRole("checkbox", { name: /God mode/ }).check();
  },
);
When(
  "an official God MCP client applies {string} while both browsers observe",
  async ({ state }, scenario: string) => {
    state.scenario = scenario;
    const result = await call("god", "apply_fault", {
      scenario_id: scenario,
      idempotency_key: crypto.randomUUID(),
    });
    expect(result.data.verified).toBe(true);
  },
);
Then(
  "God sees the fixed scenario and Operator sees only factual routing evidence",
  async ({ state }) => {
    await expect(state.god.getByLabel("Controller ground truth")).toContainText(
      state.scenario!,
      { timeout: 20000 },
    );
    await expect(
      state.operator.getByLabel("Controller ground truth"),
    ).toHaveCount(0);
    const response = await state.operator.request.get("/api/v1/topology");
    expect((await response.json()).controller).toBeUndefined();
    await state.operator
      .getByRole("button", { name: "Prefix", exact: true })
      .click();
    await expect(
      state.operator
        .getByRole("table", { name: "Exact prefix evidence" })
        .locator("tbody tr"),
    ).toHaveCount(6);
    await expect(
      state.operator.getByRole("region", { name: "Routing layers" }),
    ).toContainText("6/6 collected", { timeout: 20000 });
    if (state.scenario === "data-path-degradation") {
      const probe = await call("operator", "ping", {
        node_id: "ce1",
        destination: "10.200.8.2",
        count: 5,
      });
      expect(probe.data.received).toBeGreaterThan(0);
      expect(probe.data.rtt_ms.avg).toBeGreaterThanOrEqual(75);
    } else {
      const result = await call("operator", "get_interfaces", {
        node_id: state.scenario === "core-link-failure" ? "p1" : "ce1",
        interface: state.scenario === "core-link-failure" ? "to-p2" : "to-pe1",
      });
      expect(result.data[0].flags).not.toContain("UP");
    }
    await mkdir(root + "/docs/evidence", { recursive: true });
    await state.god.screenshot({
      path: root + `/docs/evidence/${state.scenario}-god.png`,
      fullPage: true,
    });
    await state.operator.screenshot({
      path: root + `/docs/evidence/${state.scenario}-operator.png`,
      fullPage: true,
    });
  },
);
Then(
  "explicit SDK reset clears controller state and the browser receives the new generation",
  async ({ state }) => {
    const reset = await call("god", "reset_lab", {
      idempotency_key: crypto.randomUUID(),
    });
    expect(reset.generation).toBe(state.generation! + 1);
    await expect(state.god.getByLabel("Controller ground truth")).toContainText(
      "baseline",
      { timeout: 20000 },
    );
    await expect(
      state.god.getByLabel("Controller ground truth"),
    ).not.toContainText(state.scenario!);
    await expect(state.operator.locator("header")).toContainText(
      String(reset.generation),
      { timeout: 20000 },
    );
  },
);
