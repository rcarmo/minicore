import { createBdd, test } from "playwright-bdd";
import { expect } from "@playwright/test";
import { writeFile, mkdir } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
const { Then } = createBdd(test);
const exec = promisify(execFile);
Then(
  "the live workbench records timing frame heap and container samples and releases browser resources",
  async ({ page, context }) => {
    const report: any = {
      at: new Date().toISOString(),
      environment:
        "local Chromium headless SwiftShader 1440x1000; not native GPU capacity",
      api: [],
      frames: {},
      heap: [],
      containers: [],
    };
    const start = performance.now();
    await page.goto("/#p1");
    await expect(page.locator(".graph-label")).toHaveCount(8);
    report.ready_ms = performance.now() - start;
    const client = await context.newCDPSession(page);
    await client.send("Performance.enable");
    const sample = async () => {
      await client.send("HeapProfiler.collectGarbage");
      const m = await client.send("Performance.getMetrics");
      return Object.fromEntries(
        m.metrics
          .filter((v) =>
            [
              "JSHeapUsedSize",
              "Nodes",
              "JSEventListeners",
              "Documents",
            ].includes(v.name),
          )
          .map((v) => [v.name, v.value]),
      );
    };
    report.heap.push(await sample());
    for (let n = 0; n < 3; n++)
      for (const path of [
        "/api/v1/topology",
        "/api/v1/routing?prefix=10.200.8.0/29",
      ]) {
        const began = performance.now();
        const response = await page.request.get(path);
        expect(response.status()).toBe(200);
        const data = await response.json();
        if (path.includes("routing")) expect(data.data.collected).toBe(6);
        report.api.push({
          path,
          ms: performance.now() - began,
          bytes: (await response.body()).length,
        });
      }
    for (let round = 0; round < 5; round++)
      for (const layer of ["BGP", "OSPF", "AS", "Prefix"]) {
        await page.getByRole("button", { name: layer, exact: true }).click();
        if (layer === "Prefix")
          await expect(
            page.getByRole("region", { name: "Routing layers" }),
          ).toContainText("6/6 collected");
        await expect(page.locator(".graph-label")).toHaveCount(8);
      }
    report.heap.push(await sample());
    // Compare equivalent expanded states, not collapsed startup versus a full matrix.
    for (let round = 0; round < 5; round++)
      for (const layer of ["BGP", "OSPF", "AS", "Prefix"]) {
        await page.getByRole("button", { name: layer, exact: true }).click();
        if (layer === "Prefix")
          await expect(
            page.getByRole("region", { name: "Routing layers" }),
          ).toContainText("6/6 collected");
      }
    report.heap.push(await sample());
    expect(report.heap[2].Nodes).toBeLessThanOrEqual(
      report.heap[1].Nodes + 100,
    );
    expect(report.heap[2].JSEventListeners).toBeLessThanOrEqual(
      report.heap[1].JSEventListeners + 4,
    );
    expect(report.heap[2].JSHeapUsedSize).toBeLessThan(
      report.heap[1].JSHeapUsedSize + 4 * 1024 * 1024,
    );
    report.frames = await page.evaluate(async () => {
      const values: number[] = [];
      let last = performance.now();
      await new Promise<void>((resolve) => {
        const frame = (now: number) => {
          values.push(now - last);
          last = now;
          if (values.length < 120) requestAnimationFrame(frame);
          else resolve();
        };
        requestAnimationFrame(frame);
      });
      values.shift();
      values.sort((a, b) => a - b);
      return {
        samples: values.length,
        median_ms: values[Math.floor(values.length * 0.5)],
        p95_ms: values[Math.floor(values.length * 0.95)],
        max_ms: values.at(-1),
      };
    });
    const names = (
      await exec("docker", [
        "ps",
        "--filter",
        "name=minicore-",
        "--format",
        "{{.Names}}",
      ])
    ).stdout
      .trim()
      .split("\n");
    report.containers = (
      await exec("docker", [
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
        ...names,
      ])
    ).stdout
      .trim()
      .split("\n")
      .map((v) => JSON.parse(v));
    expect(report.containers).toHaveLength(9);
    expect(report.frames.samples).toBe(119);
    expect(report.ready_ms).toBeLessThan(30000);
    await client.detach();
    await page.goto("about:blank");
    expect(await page.locator(".graph-label,.protocol-label").count()).toBe(0);
    report.page_released = true;
    await mkdir("../reports", { recursive: true });
    await writeFile(
      "../reports/performance.json",
      JSON.stringify(report, null, 2) + "\n",
    );
  },
);
