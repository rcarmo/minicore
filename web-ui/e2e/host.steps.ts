import { createBdd, test as base } from "playwright-bdd";
import { expect } from "@playwright/test";
import {
  mkdtemp,
  cp,
  mkdir,
  chmod,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
  access,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
const here = dirname(fileURLToPath(import.meta.url));
async function exists(path: string) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}
async function child(args: string[], env = process.env) {
  const p = spawn(args[0], args.slice(1), { env });
  let out = "";
  p.stdout.on("data", (b) => (out += b));
  p.stderr.on("data", (b) => (out += b));
  const code = await new Promise<number>((resolve, reject) => {
    p.on("error", reject);
    p.on("close", (n) => resolve(n ?? 1));
  });
  return { code, out };
}
async function collectorCheck(name: string) {
  const result = await child(["bun", join(here, "collector.checks.ts"), name]);
  expect(result.code, result.out).toBe(0);
  expect(result.out).toContain("Verified " + name);
}
const root = join(here, "../..");
type Host = {
  dir: string;
  inventory: any;
  result: { code: number; out: string };
  before?: string[];
  secrets?: string;
};
export const test = base.extend<{ host: Host }>({
  host: async ({}, use) => {
    const dir = await mkdtemp(join(tmpdir(), "minicore-bdd-"));
    for (const d of ["scripts", "inventory", "runtime", "secrets"])
      await mkdir(join(dir, d));
    for (const f of [
      "topology.ts",
      "lab.ts",
      "init-secrets.ts",
      "log-collector.ts",
    ])
      await cp(join(root, "scripts", f), join(dir, "scripts", f));
    await cp(
      join(root, "inventory/topology.json"),
      join(dir, "inventory/topology.json"),
    );
    const inventory = JSON.parse(
      await readFile(join(dir, "inventory/topology.json"), "utf8"),
    );
    try {
      await use({ dir, inventory, result: { code: 0, out: "" } });
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  },
});
const { Given, When, Then } = createBdd(test);
async function run(
  h: Host,
  script: string,
  args: string[] = [],
  extra: Record<string, string> = {},
) {
  h.result = await child(["bun", join(h.dir, "scripts", script), ...args], {
    ...process.env,
    PATH: join(h.dir, "bin") + ":" + process.env.PATH,
    MINICORE_EXPERIMENTAL_ROUTERS: "",
    ...extra,
  });
  return h.result;
}
Given(
  "a temporary copy of the host tools and canonical inventory",
  async ({ host }) => {
    expect(host.inventory.nodes.length).toBe(8);
  },
);
When("the canonical deployment is generated twice", async ({ host }) => {
  expect((await run(host, "topology.ts")).code).toBe(0);
  host.before = await outputs(host);
  expect((await run(host, "topology.ts")).code).toBe(0);
});
async function outputs(h: Host) {
  return Promise.all(
    [
      "compose/compose.json",
      "configs/daemons",
      ...h.inventory.nodes
        .filter((n: any) => n.kind === "router")
        .map((n: any) => `configs/${n.id}/frr.conf`),
    ].map((p) => readFile(join(h.dir, p), "utf8")),
  );
}
Then("Compose and all FRR outputs are identical", async ({ host }) => {
  expect(await outputs(host)).toEqual(host.before);
});
async function compose(h: Host) {
  return JSON.parse(
    await readFile(join(h.dir, "compose/compose.json"), "utf8"),
  );
}
Then(
  "only management is in the default profile with loopback publication and no privileges",
  async ({ host }) => {
    const c = await compose(host),
      m = c.services.management;
    expect(
      Object.entries(c.services)
        .filter(([_, s]: any) => !s.profiles)
        .map(([k]) => k),
    ).toEqual(["management"]);
    expect(m.user).toBe("10001:10001");
    expect(m.cap_drop).toEqual(["ALL"]);
    expect(m.cap_add).toBeUndefined();
    expect(m.read_only).toBe(true);
    expect(m.ports[0]).toContain("127.0.0.1");
    expect(JSON.stringify(m)).not.toContain("docker.sock");
  },
);
Then(
  "all eight nodes map to declared services and nine separate data bridges",
  async ({ host }) => {
    const c = await compose(host);
    expect(Object.keys(c.services).length).toBe(9);
    for (const n of host.inventory.nodes) {
      expect(c.services[n.id].profiles).toEqual(["lab"]);
      expect(c.services[n.id].ports).toBeUndefined();
      if (n.kind === "endpoint")
        expect(c.services[n.id].networks.management).toBeUndefined();
    }
    for (const l of host.inventory.links) {
      expect(c.networks[l.network].internal).toBe(true);
      expect(l.endpoints.length).toBe(2);
      for (const e of l.endpoints)
        expect(c.services[e.node].networks[l.network].interface_name).toBe(
          e.interface,
        );
    }
  },
);
Then("endpoint gateways point at customer routers", async ({ host }) => {
  const c = await compose(host);
  expect(c.services.host1.command[2]).toContain("via 10.200.8.3");
  expect(c.services.host2.command[2]).toContain("via 10.200.9.3");
});
Then("generated artifact drift fails the check command", async ({ host }) => {
  await writeFile(join(host.dir, "configs/p1/frr.conf"), "drift");
  expect((await run(host, "topology.ts", ["--check"])).code).not.toBe(0);
});
Given(
  "the generator inventory contains {string}",
  async ({ host }, defect: string) => {
    const t = host.inventory,
      e = t.links[0].endpoints[0];
    if (defect === "duplicate service") t.nodes[1].service = t.nodes[0].service;
    else if (defect === "unknown endpoint") e.node = "alien";
    else if (defect === "invalid interface") e.interface = "../bad";
    else if (defect === "overlapping subnet")
      t.links[1].subnet = t.links[0].subnet;
    else if (defect === "gateway collision") e.address = "10.200.1.1/29";
    else throw Error(defect);
    await writeFile(
      join(host.dir, "inventory/topology.json"),
      JSON.stringify(t),
    );
  },
);
When("the canonical deployment generation is attempted", async ({ host }) => {
  await run(host, "topology.ts");
});
Then("it fails without creating deployment artifacts", async ({ host }) => {
  expect(host.result.code).not.toBe(0);
  expect(await exists(join(host.dir, "compose/compose.json"))).toBe(false);
});
Given(
  "a recording Docker executable instead of a real daemon",
  async ({ host }) => {
    await mkdir(join(host.dir, "bin"));
    const docker = join(host.dir, "bin/docker");
    await writeFile(
      docker,
      `#!/usr/bin/env bun
const args=process.argv.slice(2);
const dir=${JSON.stringify(host.dir)};
const log=dir+'/docker-calls.jsonl';
const previous=await Bun.file(log).exists()?await Bun.file(log).text():'';
await Bun.write(log,previous+JSON.stringify(args)+'\\n');
if(args.includes('ps'))console.log(JSON.stringify({Service:'p1',ID:'private-container-id',State:'running'}));
if(args.includes('logs'))console.log(new Date().toISOString()+' ERROR token=do-not-persist startup failure');
`,
    );
    await chmod(docker, 0o755);
  },
);
When(
  "the host helper requests {string} for {string} with local investigation enabled",
  async ({ host }, action: string, node: string) => {
    await run(host, "lab.ts", [action, node], {
      MINICORE_EXPERIMENTAL_ROUTERS: "1",
    });
  },
);
When(
  "the host helper requests {string} for {string} without local investigation",
  async ({ host }, action: string, node: string) => {
    await run(host, "lab.ts", [action, node]);
  },
);
async function calls(h: Host) {
  return (await readFile(join(h.dir, "docker-calls.jsonl"), "utf8"))
    .trim()
    .split("\n")
    .map((s) => JSON.parse(s));
}
Then(
  "it passes fixed Compose arguments for {string} and p1 only",
  async ({ host }, action: string) => {
    expect(host.result.code).toBe(0);
    expect(await calls(host)).toEqual([
      [
        "compose",
        "-f",
        join(host.dir, "compose/compose.json"),
        "--profile",
        "lab",
        action,
        ...(action === "up" ? ["-d"] : []),
        "p1",
      ],
    ]);
  },
);
Then("it fails without calling Docker", async ({ host }) => {
  expect(host.result.code).not.toBe(0);
  expect(await exists(join(host.dir, "docker-calls.jsonl"))).toBe(false);
});
When("the host observation helper runs", async ({ host }) => {
  await run(host, "lab.ts", ["observe"]);
});
Then(
  "the observation file contains eight logical node states and no container IDs",
  async ({ host }) => {
    expect(host.result.code).toBe(0);
    const text = await readFile(
      join(host.dir, "runtime/observations.json"),
      "utf8",
    );
    const data = JSON.parse(text);
    expect(Object.keys(data.nodes).length).toBe(8);
    expect(data.nodes.p1.container_state).toBe("running");
    expect(data.generation).toBe(1);
    expect(data.collected_at).toBeTruthy();
    expect(text).not.toContain("private-container-id");
  },
);
Then("the publication leaves no temporary file behind", async ({ host }) => {
  expect(await exists(join(host.dir, "runtime/observations.json.tmp"))).toBe(
    false,
  );
});
When("the secret initialization tool runs twice", async ({ host }) => {
  expect((await run(host, "init-secrets.ts")).code).toBe(0);
  host.secrets = await readFile(
    join(host.dir, "secrets/http/mcp-tokens.json"),
    "utf8",
  );
  const first = host.result.out;
  await run(host, "init-secrets.ts");
  host.result.out = first + host.result.out;
});
Then(
  "distinct Operator and God credentials are stored with owner-only permissions",
  async ({ host }) => {
    const data = JSON.parse(host.secrets!);
    expect(data.operator.length).toBeGreaterThanOrEqual(32);
    expect(data.god).not.toBe(data.operator);
    expect(
      (await stat(join(host.dir, "secrets/http/mcp-tokens.json"))).mode & 0o777,
    ).toBe(0o600);
  },
);
Then(
  "the second call fails without changing the credentials",
  async ({ host }) => {
    expect(host.result.code).not.toBe(0);
    expect(
      await readFile(join(host.dir, "secrets/http/mcp-tokens.json"), "utf8"),
    ).toBe(host.secrets);
  },
);
Then("neither invocation prints a credential", async ({ host }) => {
  for (const secret of Object.values(JSON.parse(host.secrets!)))
    expect(host.result.out).not.toContain(secret as string);
});
Then(
  "the collector removes recognized credentials and private keys but retains ordinary event text",
  async () => {
    await collectorCheck("redaction");
  },
);
Then(
  "repeated messages have stable distinct IDs within a container incarnation and snapshots fit the size cap",
  async () => {
    await collectorCheck("identities");
  },
);
Then("the collector kills over-limit and timed-out children", async () => {
  await collectorCheck("commandBounds");
});
Then(
  "long log messages are truncated and old or malformed lines are excluded",
  async () => {
    await collectorCheck("messageBounds");
  },
);
When("the log collector runs once", async ({ host }) => {
  await run(host, "log-collector.ts", ["--once"]);
});
Then(
  "only inventoried node services are requested with timestamp, tail and time-window bounds",
  async ({ host }) => {
    expect(host.result.code).toBe(0);
    const list = await calls(host);
    expect(list.length).toBe(2);
    expect(list[1].slice(5)).toEqual([
      "logs",
      "--no-color",
      "--no-log-prefix",
      "--timestamps",
      "--tail",
      "501",
      "--since",
      "15m",
      "p1",
    ]);
  },
);
Then(
  "atomic log snapshots contain no management records or raw credentials",
  async ({ host }) => {
    const dir = join(host.dir, "runtime/node-logs"),
      files = await readdir(dir);
    expect(files.sort()).toEqual(
      host.inventory.nodes.map((n: any) => n.id + ".json").sort(),
    );
    const text = await readFile(join(dir, "p1.json"), "utf8");
    expect(text).not.toContain("do-not-persist");
    expect(text).not.toContain("private-container-id");
    expect(JSON.parse(text).entries.length).toBe(1);
    expect(await exists(join(dir, "p1.json.tmp"))).toBe(false);
  },
);
Then("the collector removes its lock on exit", async ({ host }) => {
  expect(
    (await readdir(join(host.dir, "runtime"))).includes("log-collector.lock"),
  ).toBe(false);
});
When("the log collector requests an unknown node", async ({ host }) => {
  await run(host, "log-collector.ts", ["--once", "--node", "alien"]);
});
Given("a collector lock already exists", async ({ host }) => {
  await mkdir(join(host.dir, "runtime/log-collector.lock"));
});
Then("it fails without removing another collector's lock", async ({ host }) => {
  expect(host.result.code).not.toBe(0);
  expect(
    (await readdir(join(host.dir, "runtime"))).includes("log-collector.lock"),
  ).toBe(true);
});
Then(
  "every implemented scenario has exactly one execution runner and no planned scenario can masquerade as implemented",
  async () => {
    const result = await child([
      "bun",
      "test",
      join(root, "web-ui/src/feature-inventory.test.ts"),
    ]);
    expect(result.code, result.out).toBe(0);
    expect(result.out).toContain("0 fail");
  },
);
Then(
  "a passing report with an outline renamed to another behavior fails the acceptance gate",
  async () => {
    const result = await child([
      "bun",
      "test",
      join(root, "web-ui/src/acceptance-report.test.ts"),
    ]);
    expect(result.code, result.out).toBe(0);
    expect(result.out).toContain("0 fail");
  },
);
Then(
  "router services build the reviewed image without SYS_ADMIN and check every required daemon",
  async ({ host }) => {
    const c = await compose(host);
    for (const id of ["p1", "p2", "pe1", "pe2", "ce1", "ce2"]) {
      expect(c.services[id].image).toBe("minicore-router:10.4.1-plain");
      expect(c.services[id].build.dockerfile).toBe("router-image/Dockerfile");
      expect(c.services[id].cap_add).not.toContain("SYS_ADMIN");
      expect(c.services[id].healthcheck.test).toEqual([
        "CMD",
        "/usr/local/bin/node-health",
      ]);
    }
  },
);
Then(
  "each node mounts its own declared configuration files",
  async ({ host }) => {
    const c = await compose(host);
    for (const id of ["p1", "p2", "pe1", "pe2", "ce1", "ce2"])
      expect(c.services[id].volumes).toContain(
        `../configs/${id}/daemons:/etc/frr/daemons:ro`,
      );
  },
);
Then(
  "management mounts only its HTTP credential directory and diagnostic client keys, never the parent secrets tree",
  async ({ host }) => {
    const c = await compose(host);
    expect(c.services.management.volumes).not.toContain(
      "../secrets:/run/secrets:ro",
    );
    expect(c.services.management.volumes).toContain(
      "../secrets/http:/run/secrets:ro",
    );
    expect(c.services.management.volumes).toContain(
      "../secrets/ssh/client:/run/ssh-client:ro",
    );
  },
);
