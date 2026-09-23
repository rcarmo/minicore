import { describe, expect, test } from "bun:test";
import { topologyChanged, validateSnapshot } from "./topology";

const snapshot = {
  schema_version: "1.0",
  lab_id: "minicore",
  generation: 1,
  revision: "r1",
  collected_at: "2026-01-01T00:00:00Z",
  source: "combined",
  runtime_status: "not_configured",
  nodes: [],
  links: [],
} as const;
describe("topology contract", () => {
  test("accepts a versioned snapshot", () =>
    expect(validateSnapshot(snapshot).revision).toBe("r1"));
  test("rejects unsupported schemas", () =>
    expect(() =>
      validateSnapshot({ ...snapshot, schema_version: "2" }),
    ).toThrow());
  test("uses revision and generation for reconciliation", () => {
    expect(
      topologyChanged(validateSnapshot(snapshot), validateSnapshot(snapshot)),
    ).toBeFalse();
    expect(
      topologyChanged(
        validateSnapshot(snapshot),
        validateSnapshot({ ...snapshot, generation: 2 }),
      ),
    ).toBeTrue();
  });
});

test("rejects malformed geometry and dangling links", () => {
  expect(() =>
    validateSnapshot({ ...snapshot, nodes: [{ id: "p1" }] }),
  ).toThrow();
  expect(() =>
    validateSnapshot({
      ...snapshot,
      links: [{ id: "bad", source: "p1", target: "p2", state: "unknown" }],
    }),
  ).toThrow();
});
