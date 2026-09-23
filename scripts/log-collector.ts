/** Host-only bounded container-log collector; never included in the management image. */
import { createHash } from "node:crypto";
import { mkdir, rename, rm } from "node:fs/promises";
import { join } from "node:path";
import { loadTopology, root, type Node, type Topology } from "./topology";

const MAX_OUTPUT = 256 * 1024;
export const MAX_SNAPSHOT = 60 * 1024;
export interface Entry {
  id: string;
  timestamp: string;
  source: "container";
  severity: "error" | "warning" | "info" | "unknown";
  message: string;
  truncated: boolean;
}
export interface LogSnapshot {
  schema_version: "1.0";
  lab_id: string;
  generation: number;
  node_id: string;
  source: "container";
  collected_at: string;
  window_start: string;
  status: "ok" | "unavailable";
  error_code: string | null;
  entries: Entry[];
  truncated: boolean;
  revision: string;
}
const hash = (s: string) =>
  createHash("sha256").update(s).digest("hex").slice(0, 24);

export function redact(text: string, secrets: string[] = []): string {
  let value = text
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/[\x00-\x08\x0b-\x1f\x7f]/g, "");
  for (const secret of secrets)
    if (secret) value = value.split(secret).join("[REDACTED]");
  return value
    .replace(/\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+/gi, "$1 [REDACTED]")
    .replace(
      /((?:password|passwd|token|secret|api[_-]?key|authorization)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi,
      "$1[REDACTED]",
    )
    .replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi, "$1[REDACTED]@");
}

export function parseLines(
  output: string,
  identity: string,
  secrets: string[],
  now = Date.now(),
) {
  const entries: Entry[] = [];
  const occurrences = new Map<string, number>();
  let privateKey = false;
  for (const line of output.split(/\r?\n/)) {
    const match = /^(\d{4}-\d\d-\d\dT\S+Z)\s+(.*)$/.exec(line);
    if (!match) continue;
    const timestamp = match[1],
      time = Date.parse(timestamp);
    if (!Number.isFinite(time) || time < now - 15 * 60_000 || time > now + 5000)
      continue;
    const raw = match[2];
    // Container stdout is not a source for arbitrary block credentials. Drop PEM bodies.
    if (/-----BEGIN .*PRIVATE KEY-----/.test(raw)) {
      privateKey = true;
      continue;
    }
    if (/-----END .*PRIVATE KEY-----/.test(raw)) {
      privateKey = false;
      continue;
    }
    if (privateKey || /^[A-Za-z0-9+/=]{40,}$/.test(raw.trim())) continue;
    const sanitized = redact(raw, secrets);
    const bytes = Buffer.from(sanitized);
    const message = bytes
      .subarray(0, 2048)
      .toString("utf8")
      .replace(/\ufffd$/, " ");
    const basis = timestamp + "\0" + sanitized;
    const occurrence = occurrences.get(basis) ?? 0;
    occurrences.set(basis, occurrence + 1);
    // Hash includes incarnation identity, but Docker IDs never reach the UI.
    entries.push({
      id: hash(identity + "\0" + basis + "\0" + occurrence),
      timestamp,
      source: "container",
      severity: /\b(error|failed|failure|fatal|panic)\b/i.test(message)
        ? "error"
        : /\bwarn(?:ing)?\b/i.test(message)
          ? "warning"
          : /\binfo(?:rmational)?\b/i.test(message)
            ? "info"
            : "unknown",
      message,
      truncated: bytes.length > 2048,
    });
  }
  return entries.sort(
    (a, b) =>
      b.timestamp.localeCompare(a.timestamp) || a.id.localeCompare(b.id),
  );
}

export function boundedSnapshot(
  t: Topology,
  node: Node,
  entries: Entry[],
  error: string | null,
  clipped = false,
): LogSnapshot {
  const snapshot: LogSnapshot = {
    schema_version: "1.0",
    lab_id: t.lab_id,
    generation: t.generation,
    node_id: node.id,
    source: "container",
    collected_at: new Date().toISOString(),
    window_start: new Date(Date.now() - 900_000).toISOString(),
    status: error ? "unavailable" : "ok",
    error_code: error,
    entries: entries.slice(0, 500),
    truncated: clipped || entries.length > 500,
    revision: "",
  };
  while (
    Buffer.byteLength(JSON.stringify(snapshot)) > MAX_SNAPSHOT - 100 &&
    snapshot.entries.length
  ) {
    snapshot.entries.pop();
    snapshot.truncated = true;
  }
  snapshot.revision = hash(
    JSON.stringify([
      t.generation,
      snapshot.status,
      error,
      snapshot.entries,
      snapshot.truncated,
    ]),
  );
  return snapshot;
}

export async function boundedCommand(
  args: string[],
  signal: AbortSignal,
  deadlineMs = 5000,
) {
  const proc = Bun.spawn(args, {
    stdout: "pipe",
    stderr: "pipe",
    stdin: "ignore",
  });
  let length = 0,
    clipped = false,
    timedOut = false;
  const stop = () => {
    proc.kill("SIGKILL");
  };
  signal.addEventListener("abort", stop, { once: true });
  if (signal.aborted) stop();
  const timer = setTimeout(() => {
    timedOut = true;
    stop();
  }, deadlineMs);
  const read = async (stream: ReadableStream<Uint8Array>) => {
    const buffers: Uint8Array[] = [];
    const reader = stream.getReader();
    try {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        const remaining = MAX_OUTPUT - length;
        if (value.length > remaining) {
          clipped = true;
          buffers.push(value.subarray(0, remaining));
          length = MAX_OUTPUT;
          stop();
          break;
        }
        length += value.length;
        buffers.push(value);
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    return Buffer.concat(buffers).toString("utf8");
  };
  try {
    const outputs = await Promise.all([read(proc.stdout), read(proc.stderr)]);
    const code = await proc.exited;
    return {
      output: outputs.filter(Boolean).join("\n"),
      code,
      clipped,
      timedOut,
    };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", stop);
    if (proc.exitCode === null) stop();
    await proc.exited;
  }
}

async function collect(
  t: Topology,
  nodes: Node[],
  signal: AbortSignal,
  secrets: string[],
) {
  const base = [
    "docker",
    "compose",
    "-f",
    join(root, "compose/compose.json"),
    "--profile",
    "lab",
  ];
  const status = await boundedCommand(
    [...base, "ps", "--all", "--format", "json"],
    signal,
  );
  let records: { Service: string; ID: string; State: string }[] = [];
  let statusError: string | null = null;
  try {
    if (status.timedOut || status.clipped || status.code) throw Error();
    records = status.output.trim()
      ? status.output
          .trim()
          .split("\n")
          .flatMap((line) => JSON.parse(line))
      : [];
    if (
      !Array.isArray(records) ||
      records.some(
        (r) =>
          typeof r.Service !== "string" ||
          typeof r.ID !== "string" ||
          typeof r.State !== "string",
      )
    )
      throw Error();
  } catch {
    statusError = status.timedOut ? "collection_timeout" : "collection_failed";
  }
  // At most two child log commands at once. No follow children or growing buffers.
  for (let i = 0; i < nodes.length && !signal.aborted; i += 2)
    await Promise.all(
      nodes.slice(i, i + 2).map(async (node) => {
        const record = records.find((r) => r.Service === node.service);
        let error = statusError ?? (!record ? "node_unavailable" : null),
          entries: Entry[] = [],
          clipped = false;
        if (record && !statusError) {
          const result = await boundedCommand(
            [
              ...base,
              "logs",
              "--no-color",
              "--no-log-prefix",
              "--timestamps",
              "--tail",
              "501",
              "--since",
              "15m",
              node.service,
            ],
            signal,
          );
          clipped = result.clipped;
          error = result.timedOut
            ? "collection_timeout"
            : result.code && !result.clipped
              ? "collection_failed"
              : record.State !== "running"
                ? "node_unavailable"
                : null;
          entries = parseLines(
            result.output,
            `${t.lab_id}:${t.generation}:${node.id}:${record.ID}`,
            secrets,
          );
          // Incomplete output could end in a partial credential line. Discard that sample.
          if (result.clipped) {
            entries = [];
            error = "output_limit";
          }
        }
        const dir = join(root, "runtime/node-logs");
        await mkdir(dir, { recursive: true });
        const file = join(dir, `${node.id}.json`);
        await Bun.write(
          file + ".tmp",
          JSON.stringify(boundedSnapshot(t, node, entries, error, clipped)),
          { mode: 0o644 },
        );
        await rename(file + ".tmp", file);
      }),
    );
}

export async function main(args = process.argv.slice(2)) {
  const t = await loadTopology();
  let once = false,
    duration = 600,
    node: string | undefined;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--once") once = true;
    else if (args[i] === "--duration") {
      duration = Number(args[++i]);
      if (!Number.isInteger(duration) || duration < 1 || duration > 3600)
        throw Error("Duration must be 1–3600 seconds");
    } else if (args[i] === "--node") node = args[++i] ?? "";
    else
      throw Error(
        "Allowed options: --once --duration 1..3600 --node inventory-id",
      );
  }
  if (node !== undefined && !t.nodes.some((n) => n.id === node))
    throw Error("Unknown inventory node");
  const dir = join(root, "runtime");
  await mkdir(dir, { recursive: true });
  const lock = join(dir, "log-collector.lock");
  try {
    await mkdir(lock);
  } catch {
    throw Error(
      "Collector already running or stale runtime/log-collector.lock; verify before removing it",
    );
  }
  const abort = new AbortController();
  const stop = () => abort.abort();
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
  const deadline = setTimeout(stop, duration * 1000);
  try {
    const credentialFile = Bun.file(join(root, "secrets/http/mcp-tokens.json"));
    let secrets: string[] = [];
    if (await credentialFile.exists()) {
      const credentials = await credentialFile.json();
      secrets = Object.values(credentials).filter(
        (v): v is string => typeof v === "string",
      );
    }
    console.log(
      `Collecting bounded node logs${node ? ` for ${node}` : ""}; Ctrl-C stops; expires after ${duration}s`,
    );
    do {
      await collect(
        t,
        node ? t.nodes.filter((n) => n.id === node) : t.nodes,
        abort.signal,
        secrets,
      );
      if (once || abort.signal.aborted) break;
      await new Promise<void>((resolve) => {
        const done = () => {
          clearTimeout(timer);
          abort.signal.removeEventListener("abort", done);
          resolve();
        };
        const timer = setTimeout(done, 2000);
        abort.signal.addEventListener("abort", done, { once: true });
      });
    } while (!abort.signal.aborted);
  } finally {
    clearTimeout(deadline);
    process.removeListener("SIGINT", stop);
    process.removeListener("SIGTERM", stop);
    await rm(lock, { recursive: true });
  }
}
if (import.meta.main) await main();
