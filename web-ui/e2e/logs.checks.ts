import { expect, type Page } from "@playwright/test";

function pageFor(
  node: string,
  revision: number,
  message = `event ${revision}`,
) {
  return {
    node_id: node,
    generation: 1,
    collected_at: new Date().toISOString(),
    status: "ok",
    error_code: null,
    truncated: false,
    data: {
      revision: String(revision),
      source: "container",
      entries: [
        {
          id: `entry-${revision}`,
          timestamp: new Date().toISOString(),
          source: "container",
          severity: "error",
          message,
          truncated: false,
        },
      ],
      next_cursor: revision === 1 ? "older" : null,
      retained_count: 1,
    },
  };
}

export async function followPausePaging({ page }: { page: Page }) {
  let revision = 1;
  await page.route(
    /\/api\/v1\/nodes\/[^/]+\/logs(?:[/?].*)?$/,
    async (route) => {
      const url = new URL(route.request().url()),
        node = url.pathname.split("/")[4];
      if (url.pathname.endsWith("/events"))
        return route.fulfill({
          contentType: "text/event-stream",
          body: `retry: 500\nevent: logs.snapshot\ndata: ${JSON.stringify({ node_id: node, revision: String(revision) })}\n\n`,
        });
      const older = url.searchParams.has("cursor");
      return route.fulfill({
        json: pageFor(
          node,
          older ? 0 : revision,
          older
            ? "older event"
            : `${node}: event ${revision} <img src=x onerror="window.compromised=true">`,
        ),
      });
    },
  );
  await page.goto("/#p1");
  await page.getByRole("button", { name: "Logs", exact: true }).click();
  const rows = page.getByLabel("Node log entries");
  await expect(rows).toContainText("p1: event 1 <img");
  expect(await page.locator(".log-entry img").count()).toBe(0);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  revision = 2;
  await expect(
    page.getByText("New log entries available.", { exact: false }),
  ).toBeVisible({ timeout: 10000 });
  await expect(rows).toContainText("event 1");
  await page
    .getByRole("button", { name: "Follow latest", exact: true })
    .click();
  await expect(rows).toContainText("event 2");
  await expect(page.locator(".log-entry")).toHaveCount(1);
  revision = 1;
  await page.getByRole("button", { name: "Latest", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Older", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Older", exact: true }).click();
  await expect(rows).toContainText("older event");
  await expect(
    page.getByRole("button", { name: "Follow latest", exact: true }),
  ).toBeVisible();
  await page.locator(".graph-label").filter({ hasText: /^P2$/ }).click();
  await expect(rows).toContainText("p2: event 1");
  await expect(rows).not.toContainText("p1:");
  expect(await page.evaluate(() => Boolean((window as any).compromised))).toBe(
    false,
  );
}

export async function pollingFallback({ page }: { page: Page }) {
  let revision = 1;
  await page.route(/\/api\/v1\/nodes\/p1\/logs(?:[/?].*)?$/, (route) =>
    route.request().url().endsWith("/events")
      ? route.fulfill({ status: 503, body: "unavailable" })
      : route.fulfill({ json: pageFor("p1", revision) }),
  );
  await page.goto("/#p1");
  await page.getByRole("button", { name: "Logs", exact: true }).click();
  await expect(page.getByLabel("Node log entries")).toContainText("event 1");
  revision = 2;
  await expect(page.getByLabel("Node log entries")).toContainText("event 2", {
    timeout: 10000,
  });
  await expect(
    page.getByText("reconnecting; polling continues", { exact: false }),
  ).toBeVisible();
}

export async function selectionRace({ page }: { page: Page }) {
  await page.route(
    /\/api\/v1\/nodes\/[^/]+\/logs(?:[/?].*)?$/,
    async (route) => {
      const url = new URL(route.request().url()),
        node = url.pathname.split("/")[4];
      if (url.pathname.endsWith("/events"))
        return route.fulfill({ status: 503, body: "" });
      if (node === "p1")
        await new Promise((resolve) => setTimeout(resolve, 1000));
      await route
        .fulfill({ json: pageFor(node, 1, node + " only") })
        .catch(() => {});
    },
  );
  await page.goto("/#p1");
  await page.getByRole("button", { name: "Logs", exact: true }).click();
  await page.locator(".graph-label").filter({ hasText: /^P2$/ }).click();
  await expect(page.getByLabel("Node log entries")).toContainText("p2 only");
  await page.waitForTimeout(1300);
  await expect(page.getByLabel("Node log entries")).not.toContainText(
    "p1 only",
  );
}
