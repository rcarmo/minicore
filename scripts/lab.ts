/** Host-side, inventory-bounded Compose lifecycle. Never installed in the MCP container. */
import { join } from "node:path";
import { rename } from "node:fs/promises";
import { loadTopology, root } from "./topology";
const t = await loadTopology();
const [action = "status", node] = process.argv.slice(2);
const allowed = ["up", "stop", "start", "restart", "status", "observe"];
if (!allowed.includes(action))
  throw Error(`Action must be one of ${allowed.join(", ")}`);
if (node && !t.nodes.some((n) => n.id === node))
  throw Error("Unknown inventory node");
const base = [
  "docker",
  "compose",
  "-f",
  join(root, "compose/compose.json"),
  "--profile",
  "lab",
];
if (action === "observe" || action === "status") {
  const proc = Bun.spawn([...base, "ps", "--all", "--format", "json"], {
    stdout: "pipe",
    stderr: "inherit",
  });
  const text = await new Response(proc.stdout).text();
  if (await proc.exited) throw Error("Compose status failed");
  const records = text.trim()
    ? text
        .trim()
        .split("\n")
        .flatMap((line) => JSON.parse(line))
    : [];
  const nodes = Object.fromEntries(
    t.nodes.map((n) => {
      const item = records.find((r) => r.Service === n.service);
      return [n.id, { container_state: item?.State ?? "missing" }];
    }),
  );
  const payload = {
    schema_version: "1.0",
    lab_id: t.lab_id,
    generation: t.generation,
    collected_at: new Date().toISOString(),
    nodes,
  };
  if (action === "observe") {
    const file = join(root, "runtime/observations.json");
    await Bun.write(file + ".tmp", JSON.stringify(payload, null, 2));
    await rename(file + ".tmp", file);
  }
  console.log(JSON.stringify(payload, null, 2));
} else {
  const services = node
    ? [t.nodes.find((n) => n.id === node)!.service]
    : t.nodes.map((n) => n.service);
  const args =
    action === "up" ? ["up", "-d", ...services] : [action, ...services];
  const proc = Bun.spawn([...base, ...args], {
    stdin: "inherit",
    stdout: "inherit",
    stderr: "inherit",
  });
  process.exit(await proc.exited);
}
