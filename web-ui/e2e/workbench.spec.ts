import { test, expect } from "@playwright/test";

test("full brief topology, node selection and bounded logs unavailable", async ({
  page,
}) => {
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
});

test("WebGL failure still exposes topology and selection", async ({ page }) => {
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
});

test("tablet layout and selection survive snapshot updates", async ({
  page,
}) => {
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
});
