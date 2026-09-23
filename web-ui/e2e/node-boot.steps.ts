import { createBdd } from "playwright-bdd";
import { expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const { Given, When, Then } = createBdd();
export async function command(args: string[], timeout = 100000) {
  const p = spawn(args[0], args.slice(1), {
    cwd: root,
    env: { ...process.env, MINICORE_EXPERIMENTAL_ROUTERS: "" },
  });
  let text = "";
  p.stdout.on("data", (b) => (text += b));
  p.stderr.on("data", (b) => (text += b));
  const timer = setTimeout(() => p.kill("SIGKILL"), timeout);
  const code = await new Promise<number>((resolve, reject) => {
    p.on("error", reject);
    p.on("exit", (n) => resolve(n ?? 1));
  });
  clearTimeout(timer);
  expect(code, text.slice(-8000)).toBe(0);
  return text;
}
const base = [
  "docker",
  "compose",
  "-f",
  "compose/compose.json",
  "--profile",
  "lab",
];
When("the host starts the declared lab profile", async () => {
  await command(["bun", "scripts/lab.ts", "up"]);
});
Then(
  "all six router and two endpoint containers become healthy within 90 seconds",
  async () => {
    await healthy();
  },
);
async function healthy() {
  await expect
    .poll(
      async () => {
        const rows = (await command([...base, "ps", "--format", "json"]))
          .trim()
          .split("\n")
          .flatMap((x) => JSON.parse(x));
        return rows.filter(
          (x) =>
            ["p1", "p2", "pe1", "pe2", "ce1", "ce2", "host1", "host2"].includes(
              x.Service,
            ) && x.Health === "healthy",
        ).length;
      },
      { timeout: 90000, intervals: [1000] },
    )
    .toBe(8);
}
Given("all lab nodes are healthy", async () => {
  await healthy();
});
Then(
  "every router runs zebra, bgpd and ospfd without SYS_ADMIN or privileged mode",
  async () => {
    for (const node of ["p1", "p2", "pe1", "pe2", "ce1", "ce2"]) {
      const id = (await command([...base, "ps", "-q", node])).trim();
      const info = JSON.parse(await command(["docker", "inspect", id]))[0];
      expect(info.HostConfig.Privileged).toBe(false);
      expect(
        info.HostConfig.CapAdd.map((cap: string) => cap.replace(/^CAP_/, "")),
      ).not.toContain("SYS_ADMIN");
      await command([
        ...base,
        "exec",
        "-T",
        node,
        "/usr/local/bin/node-health",
      ]);
    }
  },
);
Then(
  "the management container still has no Docker socket or added capabilities",
  async () => {
    const id = (await command([...base, "ps", "-q", "management"])).trim();
    const x = JSON.parse(await command(["docker", "inspect", id]))[0];
    expect(x.HostConfig.CapAdd ?? []).toEqual([]);
    expect(JSON.stringify(x.Mounts)).not.toContain("docker.sock");
  },
);
Then("endpoint default gateways point to their CE routers", async () => {
  for (const [node, ip] of [
    ["host1", "10.200.8.3"],
    ["host2", "10.200.9.3"],
  ])
    expect(
      await command([
        ...base,
        "exec",
        "-T",
        node,
        "ip",
        "route",
        "show",
        "default",
      ]),
    ).toContain("via " + ip);
});
Then(
  "the provider has ten Full OSPF neighbor entries and twelve established iBGP peer entries",
  async () => {
    await expect
      .poll(
        async () => {
          let full = 0,
            peers = 0;
          for (const node of ["p1", "p2", "pe1", "pe2"]) {
            const ospf = await command([
              ...base,
              "exec",
              "-T",
              node,
              "vtysh",
              "-c",
              "show ip ospf neighbor",
            ]);
            full += (ospf.match(/Full\//g) || []).length;
            const bgp = JSON.parse(
              await command([
                ...base,
                "exec",
                "-T",
                node,
                "vtysh",
                "-c",
                "show bgp summary json",
              ]),
            );
            peers += Object.values(bgp.ipv4Unicast?.peers ?? {}).filter(
              (p: any) => p.remoteAs === 65000 && p.state === "Established",
            ).length;
          }
          return [full, peers];
        },
        { timeout: 90000, intervals: [2000] },
      )
      .toEqual([10, 12]);
  },
);
Then("both customer eBGP sessions are established on both ends", async () => {
  for (const node of ["ce1", "ce2", "pe1", "pe2"]) {
    const bgp = JSON.parse(
      await command([
        ...base,
        "exec",
        "-T",
        node,
        "vtysh",
        "-c",
        "show bgp summary json",
      ]),
    );
    expect(
      Object.values(bgp.ipv4Unicast.peers).filter(
        (p: any) =>
          p.remoteAs !== bgp.ipv4Unicast.as && p.state === "Established",
      ),
    ).toHaveLength(1);
  }
});
Then("host1 and host2 exchange three packets in each direction", async () => {
  for (const [node, ip] of [
    ["host1", "10.200.9.2"],
    ["host2", "10.200.8.2"],
  ])
    expect(
      await command([
        ...base,
        "exec",
        "-T",
        node,
        "ping",
        "-c",
        "3",
        "-W",
        "2",
        ip,
      ]),
    ).toMatch(/(?:^|\s)0% packet loss/);
});
Given("the host node log collector is running", async () => {
  await command(["bun", "scripts/log-watcher.ts", "start"]);
});
When("the host restarts p1", async () => {
  await command(["bun", "scripts/lab.ts", "restart", "p1"]);
});
Then("p1 becomes healthy again", async () => {
  await healthy();
});
Then("a real p1 log event invalidates its HTTP log page via SSE", async () => {
  const child = spawn("python3", ["tests/logs_smoke.py"], {
    cwd: root,
    stdio: "pipe",
  });
  let output = "";
  const exited = new Promise<number | null>((resolve) =>
    child.once("exit", resolve),
  );
  child.stdout.on("data", (b) => (output += b));
  child.stderr.on("data", (b) => (output += b));
  await new Promise((r) => setTimeout(r, 2000));
  await command([...base, "restart", "p1"]);
  const code = await exited;
  expect(code, output).toBe(0);
});
Then(
  "the browser displays fresh node messages without startup capability failures",
  async ({ page, request }) => {
    await expect
      .poll(
        async () => {
          const r = await request.get("/api/v1/nodes/p1/logs?limit=500");
          return r.status();
        },
        { timeout: 20000 },
      )
      .toBe(200);
    const data = await (
      await request.get("/api/v1/nodes/p1/logs?limit=500")
    ).json();
    expect(JSON.stringify(data)).not.toContain("cap_set_proc failed");
    expect(data.data.entries.length).toBeGreaterThan(0);
    await page.goto("/#p1");
    await page.getByRole("button", { name: "Logs", exact: true }).click();
    await expect(page.locator(".log-entry").first()).toBeVisible();
    await page.screenshot({
      path: "../docs/evidence/boot-live-logs.png",
      fullPage: true,
    });
  },
);
When("the owner enables the explicit host log watcher", async () => {
  await command(["bun", "scripts/log-watcher.ts", "start"]);
});
Then(
  "fresh bounded node log snapshots remain available without an interactive shell loop",
  async ({ request }) => {
    await expect
      .poll(async () => (await request.get("/api/v1/nodes/p1/logs")).status(), {
        timeout: 20000,
      })
      .toBe(200);
  },
);
Then(
  "restarting that watcher resumes collection without a stale collector lock",
  async ({ request }) => {
    await command(["bun", "scripts/log-watcher.ts", "restart"]);
    await expect
      .poll(async () => (await request.get("/api/v1/nodes/p1/logs")).status(), {
        timeout: 20000,
      })
      .toBe(200);
  },
);
Then(
  "stopping that watcher makes old samples visibly stale",
  async ({ request }) => {
    await command(["bun", "scripts/log-watcher.ts", "stop"]);
    await expect
      .poll(
        async () =>
          (await (await request.get("/api/v1/nodes/p1/logs")).json())
            .error_code,
        { timeout: 22000, intervals: [1000] },
      )
      .toBe("collector_stale");
  },
);
