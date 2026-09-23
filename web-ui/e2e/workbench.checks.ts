import { expect, type Page } from "@playwright/test";

export async function graphSelection({ page }: { page: Page }) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByText("8 nodes / 9 links")).toBeVisible();
  await expect(page.locator(".graph-label")).toHaveCount(8);
  await page.locator(".graph-label").filter({ hasText: /^PE1$/ }).click();
  await expect(
    page.getByRole("heading", { name: "PE1", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Logs", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText(
    /Logs unavailable: (backend_not_configured|node_unavailable|collector_stale)/,
  );
  await expect(page.getByText("connected", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../docs/evidence/workbench.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
}

export async function webglFallback({ page }: { page: Page }) {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: any,
      ...args: any[]
    ): any {
      return type === "webgl2"
        ? null
        : original.apply(this, [type, ...args] as any);
    };
  });
  await page.goto("/");
  await expect(page.getByText("8 nodes / 9 links")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("WebGL2 unavailable");
  await page.getByRole("button", { name: "CE2", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "CE2", exact: true }),
  ).toBeVisible();
}

export async function tabletPolling({ page }: { page: Page }) {
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/");
  await expect(page.locator(".graph-label")).toHaveCount(8);
  await page.locator(".graph-label").filter({ hasText: /^P1$/ }).click();
  await expect(
    page.getByRole("heading", { name: "P1", exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(16000);
  await expect(
    page.getByRole("heading", { name: "P1", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../docs/evidence/workbench-tablet.png",
    fullPage: true,
  });
}

export async function cameraControls({ page }: { page: Page }) {
  await page.goto("/");
  await expect(page.locator(".graph-label")).toHaveCount(8);
  const position = () =>
    page
      .locator(".graph-label")
      .filter({ hasText: /^P1$/ })
      .evaluate((el) => [
        el.getBoundingClientRect().x,
        el.getBoundingClientRect().y,
      ]);
  const before = await position();
  const canvas = page.getByLabel("Interactive network topology");
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box.x + box.width / 2 + 80,
    box.y + box.height / 2 + 30,
    { steps: 5 },
  );
  await page.mouse.up();
  await expect.poll(position).not.toEqual(before);
  const orbit = await position();
  await page.mouse.wheel(0, 250);
  await expect.poll(position).not.toEqual(orbit);
  const zoom = await position();
  await page.mouse.down({ button: "right" });
  await page.mouse.move(
    box.x + box.width / 2 + 130,
    box.y + box.height / 2 + 80,
    { steps: 5 },
  );
  await page.mouse.up({ button: "right" });
  await expect.poll(position).not.toEqual(zoom);
  await page.getByRole("button", { name: "Reset view" }).click();
  await expect
    .poll(async () => {
      const p = await position();
      return Math.abs(p[0] - before[0]) + Math.abs(p[1] - before[1]);
    })
    .toBeLessThan(1);
  await expect(page.locator(".graph-label")).toHaveCount(8);
}

export async function unavailableTabs({ page }: { page: Page }) {
  await page.goto("/#p1");
  await page.getByRole("button", { name: "Interfaces", exact: true }).click();
  await expect(
    page.getByText("Interfaces evidence unavailable: backend_not_configured"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Routing", exact: true }).click();
  await expect(
    page.getByText("Routing evidence unavailable: backend_not_configured"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Summary", exact: true }).click();
  await expect(page.getByText("Observed state", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Logs", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Logs unavailable");
}

export async function topologyReconciliation({ page }: { page: Page }) {
  await page.clock.install();
  let revision = 1,
    fetches = 0;
  await page.route("**/api/v1/topology*", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    fetches++;
    await route.fulfill({ json: { ...data, revision: "test-" + revision } });
  });
  await page.route("**/api/v1/events*", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: `retry: 1000\nevent: topology.changed\ndata: {"revision":"${revision}"}\n\n`,
    }),
  );
  await page.goto("/#p1");
  await expect(
    page.getByRole("heading", { name: "P1", exact: true }),
  ).toBeVisible();
  const initial = fetches;
  revision = 2;
  await expect(page.locator("footer")).toContainText("test-2");
  expect(fetches).toBeGreaterThan(initial);
  await page.unroute("**/api/v1/events*");
  await page.route("**/api/v1/events*", (r) =>
    r.fulfill({ status: 503, body: "" }),
  );
  // Polling is independent; fake browser clock advances only JS timers, not request completion.
  const count = fetches;
  await page.clock.fastForward(16000);
  await expect.poll(() => fetches).toBeGreaterThan(count);
  await expect(
    page.getByRole("heading", { name: "P1", exact: true }),
  ).toBeVisible();
}
