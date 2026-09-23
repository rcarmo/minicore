import { expect } from "bun:test";
import {
  boundedCommand,
  boundedSnapshot,
  parseLines,
  redact,
} from "../../scripts/log-collector";
import { loadTopology } from "../../scripts/topology";

export function redaction() {
  const stamp = new Date().toISOString();
  const text = [
    `${stamp} ERROR token=secret Bearer abc configured \x1b[31m<script>alert(1)</script>`,
    `${stamp} -----BEGIN PRIVATE KEY-----`,
    `${stamp} abcdefg`,
    `${stamp} -----END PRIVATE KEY-----`,
    `${stamp} BGP established`,
  ].join("\n");
  const entries = parseLines(text, "p1:incarnation", ["configured"]);
  expect(entries.length).toBe(2);
  // Entry hashes may contain short hex substrings; inspect the log content.
  const json = JSON.stringify(entries.map((entry) => entry.message));
  for (const s of [
    "secret",
    "abc",
    "configured",
    "abcdefg",
    "PRIVATE KEY",
    "\\u001b",
  ])
    expect(json).not.toContain(s);
  expect(json).toContain("<script>");
  expect(
    redact('https://u:pw@example.test password="long secret"'),
  ).not.toContain("pw@");
}
export async function identities() {
  const stamp = new Date().toISOString();
  const output = `${stamp} same\n${stamp} same\ninvalid\n`;
  const one = parseLines(output, "p1:a", []),
    two = parseLines(output, "p1:a", []);
  expect(one).toEqual(two);
  expect(one[0].id).not.toBe(one[1].id);
  expect(parseLines(output, "p1:b", [])[0].id).not.toBe(one[0].id);
  const t = await loadTopology();
  const snapshot = boundedSnapshot(
    t,
    t.nodes[0],
    Array.from({ length: 600 }, (_, i) => ({
      ...one[0],
      id: String(i),
      message: "a".repeat(2048),
    })),
    null,
  );
  expect(Buffer.byteLength(JSON.stringify(snapshot))).toBeLessThanOrEqual(
    60 * 1024,
  );
  expect(snapshot.entries.length).toBeLessThanOrEqual(500);
  expect(snapshot.truncated).toBe(true);
}
export async function commandBounds() {
  const abort = new AbortController();
  const limited = await boundedCommand(
    ["bun", "-e", 'process.stdout.write("x".repeat(500000));'],
    abort.signal,
  );
  expect(limited.clipped).toBe(true);
  expect(Buffer.byteLength(limited.output)).toBeLessThanOrEqual(256 * 1024);
  const timeout = await boundedCommand(
    ["bun", "-e", "setTimeout(()=>{},10000)"],
    abort.signal,
    30,
  );
  expect(timeout.timedOut).toBe(true);
}
export function messageBounds() {
  const stamp = new Date().toISOString();
  const entries = parseLines(
    `${stamp} ${"y ".repeat(3000)}\n2000-01-01T00:00:00Z old`,
    "p1",
    [],
  );
  expect(entries).toHaveLength(1);
  expect(entries[0].truncated).toBe(true);
  expect(Buffer.byteLength(entries[0].message)).toBeLessThanOrEqual(2048);
}

if (import.meta.main) {
  const actions = { redaction, identities, commandBounds, messageBounds };
  const name = process.argv[2] as keyof typeof actions;
  if (!actions[name]) throw Error("Unknown check");
  await actions[name]();
  console.log(`Verified ${name}`);
}
