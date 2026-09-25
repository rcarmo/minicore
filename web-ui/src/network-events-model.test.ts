import { describe, expect, test } from "bun:test";
import {
  buildNetworkEventsModel,
  validateObserverEnvelope,
  type ObserverEnvelope,
  type ObserverKind,
  type NetworkScope,
} from "./network-events-model";
import type { TopologySnapshot } from "./types";

const snapshot: TopologySnapshot = {
  schema_version: "1.0",
  lab_id: "lab",
  generation: 7,
  revision: "r1",
  collected_at: "2026-09-25T00:00:00Z",
  source: "combined",
  runtime_status: "available",
  nodes: [
    {
      id: "p1",
      label: "P1",
      role: "pe",
      kind: "router",
      expected: true,
      state: "up",
      position: { x: 0, y: 0, z: 0 },
      protocols: ["bgp", "ospf"],
      observed_at: "2026-09-25T00:00:00Z",
    },
    {
      id: "p2",
      label: "P2",
      role: "pe",
      kind: "router",
      expected: true,
      state: "up",
      position: { x: 1, y: 0, z: 0 },
      protocols: ["bgp", "ospf"],
      observed_at: "2026-09-25T00:00:00Z",
    },
  ],
  links: [
    {
      id: "p1-p2",
      source: "p1",
      target: "p2",
      kind: "data",
      interfaces: ["eth1", "eth1"],
      state: "up",
      expected: true,
      observed_at: "2026-09-25T00:00:00Z",
    },
  ],
};

function envelope(
  kind: ObserverKind,
  scope: NetworkScope,
  records: unknown[],
): ObserverEnvelope {
  return {
    observer_epoch: "epoch-1",
    generation: snapshot.generation,
    scope: `${scope.type}:${scope.id}:${kind}`,
    window_seconds: 60,
    source_health: "ok",
    missed_updates: 0,
    truncated: false,
    omitted: 0,
    records,
  } as ObserverEnvelope;
}

describe("network events model", () => {
  test("conservatively subtracts fetch duration and expires records by monotonic age", () => {
    const validated = validateObserverEnvelope(
      envelope("interfaces", { type: "node", id: "p1" }, [
        {
          scope: "node:p1:interfaces",
          incarnation: "inc-1",
          acquired_monotonic: 1200,
          sampled_at: "2026-09-25T00:00:00Z",
          remaining_ms: 1000,
          data: {
            interfaces: [
              {
                interface: "eth1",
                state: "UP",
                tx_packets: 10,
                rx_packets: 20,
                tx_bytes: 1000,
                rx_bytes: 2000,
                tx_errors: 0,
                rx_errors: 0,
                tx_drops: 0,
                rx_drops: 0,
              },
            ],
          },
        },
      ]),
      snapshot,
      { type: "node", id: "p1" },
      "interfaces",
      1000,
      1400,
      1400,
    );
    expect(validated.records[0]?.remainingMs).toBe(600);
    expect(
      buildNetworkEventsModel({
        snapshot,
        scope: { type: "node", id: "p1" },
        kind: "interfaces",
        current: validated,
        previous: null,
        now: 1999,
      }).rows.length,
    ).toBeGreaterThan(0);
    expect(
      buildNetworkEventsModel({
        snapshot,
        scope: { type: "node", id: "p1" },
        kind: "interfaces",
        current: validated,
        previous: null,
        now: 2001,
      }).status,
    ).toBe("Collecting…");
  });

  test("derives routing deltas only from matching healthy fresh samples", () => {
    const scope = { type: "node", id: "p1" } as const;
    const before = validateObserverEnvelope(
      envelope("routing", scope, [
        {
          scope: "node:p1:routing",
          incarnation: "inc-1",
          acquired_monotonic: 1000,
          sampled_at: "2026-09-25T00:00:00Z",
          remaining_ms: 59000,
          data: {
            peers: [{ protocol: "bgp", address: "10.0.0.2", state: "Idle" }],
            routes: [],
          },
        },
      ]),
      snapshot,
      scope,
      "routing",
      1000,
      1100,
      1100,
    );
    const after = validateObserverEnvelope(
      envelope("routing", scope, [
        {
          scope: "node:p1:routing",
          incarnation: "inc-1",
          acquired_monotonic: 1005,
          sampled_at: "2026-09-25T00:00:05Z",
          remaining_ms: 59000,
          data: {
            peers: [
              {
                protocol: "bgp",
                address: "10.0.0.2",
                state: "Established",
              },
            ],
            routes: [
              {
                prefix: "10.200.8.0/29",
                source: "bgp",
                nexthops: ["10.0.0.2"],
              },
            ],
          },
        },
      ]),
      snapshot,
      scope,
      "routing",
      5000,
      5100,
      5100,
    );
    const rows = buildNetworkEventsModel({
      snapshot,
      scope,
      kind: "routing",
      current: after,
      previous: before,
      now: 5100,
    }).rows.map((row) => row.event);
    expect(rows).toContain("Peer state changed");
    expect(rows).toContain("Route added");

    const unhealthy = {
      ...before,
      sourceHealth: "collection_timeout" as const,
    };
    const suppressed = buildNetworkEventsModel({
      snapshot,
      scope,
      kind: "routing",
      current: after,
      previous: unhealthy,
      now: 5100,
    }).rows.map((row) => row.event);
    expect(suppressed).not.toContain("Route withdrawn");
    expect(suppressed).not.toContain("Peer state changed");
  });

  test("suppresses comparisons across scope or generation changes to avoid false withdrawals", () => {
    const previous = validateObserverEnvelope(
      {
        ...envelope("routing", { type: "node", id: "p1" }, [
          {
            scope: "node:p1:routing",
            incarnation: "inc-1",
            acquired_monotonic: 1000,
            sampled_at: "2026-09-25T00:00:00Z",
            remaining_ms: 59000,
            data: {
              peers: [],
              routes: [
                {
                  prefix: "10.200.8.0/29",
                  source: "fib",
                  nexthops: ["10.0.0.2"],
                },
              ],
            },
          },
        ]),
        generation: 6,
      },
      { ...snapshot, generation: 6 },
      { type: "node", id: "p1" },
      "routing",
      1000,
      1100,
      1100,
    );
    const current = validateObserverEnvelope(
      envelope("routing", { type: "node", id: "p2" }, [
        {
          scope: "node:p2:routing",
          incarnation: "inc-2",
          acquired_monotonic: 1004,
          sampled_at: "2026-09-25T00:00:04Z",
          remaining_ms: 59000,
          data: { peers: [], routes: [] },
        },
      ]),
      snapshot,
      { type: "node", id: "p2" },
      "routing",
      4000,
      4100,
      4100,
    );
    const rows = buildNetworkEventsModel({
      snapshot,
      scope: { type: "node", id: "p2" },
      kind: "routing",
      current,
      previous,
      now: 4100,
    }).rows.map((row) => row.event);
    expect(rows).not.toContain("Route withdrawn");
  });

  test("emits interface state changes and counter resets for link projections", () => {
    const scope = { type: "link", id: "p1-p2" } as const;
    const before = validateObserverEnvelope(
      envelope("interfaces", scope, [
        {
          scope: "link:p1-p2:interfaces",
          incarnation: "inc-1",
          acquired_monotonic: 1000,
          sampled_at: "2026-09-25T00:00:00Z",
          remaining_ms: 59000,
          data: {
            interfaces: [
              {
                node_id: "p1",
                interface: "eth1",
                state: "DOWN",
                tx_packets: 100,
                rx_packets: 90,
                tx_bytes: 1000,
                rx_bytes: 900,
                tx_errors: 0,
                rx_errors: 0,
                tx_drops: 0,
                rx_drops: 0,
              },
            ],
          },
        },
      ]),
      snapshot,
      scope,
      "interfaces",
      1000,
      1100,
      1100,
    );
    const after = validateObserverEnvelope(
      envelope("interfaces", scope, [
        {
          scope: "link:p1-p2:interfaces",
          incarnation: "inc-1",
          acquired_monotonic: 1004,
          sampled_at: "2026-09-25T00:00:04Z",
          remaining_ms: 59000,
          data: {
            interfaces: [
              {
                node_id: "p1",
                interface: "eth1",
                state: "UP",
                tx_packets: 10,
                rx_packets: 5,
                tx_bytes: 100,
                rx_bytes: 50,
                tx_errors: 0,
                rx_errors: 0,
                tx_drops: 0,
                rx_drops: 0,
              },
            ],
          },
        },
      ]),
      snapshot,
      scope,
      "interfaces",
      4000,
      4100,
      4100,
    );
    const rows = buildNetworkEventsModel({
      snapshot,
      scope,
      kind: "interfaces",
      current: after,
      previous: before,
      now: 4100,
    }).rows.map((row) => row.event);
    expect(rows).toContain("Interface UP");
    expect(rows).toContain("Counters reset");
  });

  test("rejects oversized or duplicate observer data before publication", () => {
    const huge = Array.from({ length: 129 }, (_, index) => ({
      scope: "node:p1:igmp",
      incarnation: `inc-${index}`,
      acquired_monotonic: 1000 + index,
      sampled_at: "2026-09-25T00:00:00Z",
      remaining_ms: 59000,
      data: {
        version: 2,
        message_type: "report_v2",
        group: "224.0.0.1",
        reporter: "10.0.0.2",
        querier: null,
        sources: [],
        records: [],
      },
    }));
    expect(() =>
      validateObserverEnvelope(
        envelope("igmp", { type: "node", id: "p1" }, huge),
        snapshot,
        { type: "node", id: "p1" },
        "igmp",
        0,
        0,
        0,
      ),
    ).toThrow(/too large/i);

    expect(() =>
      validateObserverEnvelope(
        envelope("interfaces", { type: "node", id: "p1" }, [
          {
            scope: "node:p1:interfaces",
            incarnation: "inc-1",
            acquired_monotonic: 1000,
            sampled_at: "2026-09-25T00:00:00Z",
            remaining_ms: 59000,
            data: {
              interfaces: [
                {
                  interface: "eth1",
                  state: "UP",
                  tx_packets: 1,
                  rx_packets: 1,
                  tx_bytes: 1,
                  rx_bytes: 1,
                  tx_errors: 0,
                  rx_errors: 0,
                  tx_drops: 0,
                  rx_drops: 0,
                },
                {
                  interface: "eth1",
                  state: "UP",
                  tx_packets: 2,
                  rx_packets: 2,
                  tx_bytes: 2,
                  rx_bytes: 2,
                  tx_errors: 0,
                  rx_errors: 0,
                  tx_drops: 0,
                  rx_drops: 0,
                },
              ],
            },
          },
        ]),
        snapshot,
        { type: "node", id: "p1" },
        "interfaces",
        0,
        0,
        0,
      ),
    ).toThrow(/duplicate/i);
  });
});

const recordBase = {
  scope: "node:p1:routing",
  incarnation: "inc-1",
  acquired_monotonic: 100,
  sampled_at: "2026-09-25T00:00:00Z",
  remaining_ms: 50000,
  data: {
    peers: [{ protocol: "bgp", address: "10.254.0.2", state: "Established" }],
    routes: [{ prefix: "10.200.8.0/29", source: "rib", nexthops: [] }],
  },
};
test("regression: seconds rates and window history do not depend on prior fetch", () => {
  const topo = snapshot;
  const scope = { type: "node", id: "p1" } as const;
  const counter = (acquired: number, value: number) => ({
    scope: "node:p1:interfaces",
    incarnation: "inc-1",
    acquired_monotonic: acquired,
    sampled_at: new Date(100000 + acquired * 1000).toISOString(),
    remaining_ms: 50000,
    data: {
      interfaces: [
        {
          interface: "to-p2",
          state: "UP",
          tx_packets: value,
          rx_packets: value,
          tx_bytes: value * 10,
          rx_bytes: value * 10,
          tx_errors: 0,
          rx_errors: 0,
          tx_drops: 0,
          rx_drops: 0,
        },
      ],
    },
  });
  const raw = envelope("interfaces", scope, [counter(1, 100)]);
  raw.records = [counter(1, 100), counter(6, 150), counter(11, 200)];
  const current = validateObserverEnvelope(
    raw,
    topo,
    scope,
    "interfaces",
    0,
    0,
    0,
  );
  const result = buildNetworkEventsModel({
    snapshot: topo,
    scope,
    kind: "interfaces",
    current,
    previous: null,
    now: 1,
  });
  expect(result.sparkline.points.some((p) => p.primary === 20)).toBe(true); // 10 TX + 10 RX packets/s
  const route1 = {
    ...recordBase,
    sampled_at: "1970-01-01T00:01:40Z",
    data: {
      peers: [],
      routes: [{ prefix: "10.200.8.0/29", source: "rib", nexthops: [] }],
    },
  };
  const route2 = {
    ...route1,
    acquired_monotonic: recordBase.acquired_monotonic + 5,
    sampled_at: "1970-01-01T00:01:45Z",
    data: { peers: [], routes: [] },
  };
  const route3 = {
    ...route2,
    acquired_monotonic: recordBase.acquired_monotonic + 10,
    sampled_at: "1970-01-01T00:01:50Z",
  };
  const hist = envelope("routing", scope, [route1]);
  hist.records = [route1, route2, route3];
  const history = validateObserverEnvelope(
    hist,
    topo,
    scope,
    "routing",
    0,
    0,
    0,
  );
  expect(
    buildNetworkEventsModel({
      snapshot: topo,
      scope,
      kind: "routing",
      current: history,
      previous: null,
      now: 1,
    }).rows.filter((r) => r.event === "Route withdrawn"),
  ).toHaveLength(1);
});
test("regression: reject unbounded lifetime and invalid enums", () => {
  const topo = snapshot;
  const scope = { type: "node", id: "p1" } as const;
  for (const change of [
    (v: any) => (v.records[0].remaining_ms = 60001),
    (v: any) => (v.source_health = "healthy"),
    (v: any) => (v.records[0].sampled_at = "nonsense"),
    (v: any) => (v.records[0].data.peers[0].protocol = "http"),
  ]) {
    const raw = structuredClone(envelope("routing", scope, [recordBase]));
    change(raw);
    expect(() =>
      validateObserverEnvelope(raw, topo, scope, "routing", 0, 0, 0),
    ).toThrow();
  }
});
test("regression: truncated data does not emit withdrawals", () => {
  const scope = { type: "node", id: "p1" } as const,
    topo = snapshot;
  const previous = validateObserverEnvelope(
    envelope("routing", scope, [recordBase]),
    topo,
    scope,
    "routing",
    0,
    0,
    0,
  );
  const raw = envelope("routing", scope, [
    {
      ...recordBase,
      acquired_monotonic: recordBase.acquired_monotonic + 5,
      sampled_at: "2026-09-25T12:00:05Z",
      data: { peers: [], routes: [] },
    },
  ]);
  raw.truncated = true;
  const current = validateObserverEnvelope(
    raw,
    topo,
    scope,
    "routing",
    0,
    0,
    0,
  );
  expect(
    buildNetworkEventsModel({
      snapshot: topo,
      scope,
      kind: "routing",
      current,
      previous,
      now: 1,
    }).rows.some((r) => r.event === "Route withdrawn"),
  ).toBe(false);
});

test("regression: interleaved endpoint rate samples use matching source", () => {
  const scope = { type: "link", id: "p1-p2" } as const;
  const row = (node: string, time: number, value: number) => ({
    scope: "link:p1-p2:interfaces",
    incarnation: node + "-inc",
    acquired_monotonic: time,
    sampled_at: new Date(100000 + time * 1000).toISOString(),
    remaining_ms: 50000,
    data: {
      interfaces: [
        {
          node_id: node,
          interface: "eth1",
          state: "UP",
          tx_packets: value,
          rx_packets: 0,
          tx_bytes: value * 10,
          rx_bytes: 0,
          tx_errors: 0,
          rx_errors: 0,
          tx_drops: 0,
          rx_drops: 0,
        },
      ],
    },
  });
  const raw = envelope("interfaces", scope, [
    row("p1", 1, 10),
    row("p2", 2, 20),
    row("p1", 6, 60),
    row("p2", 7, 120),
  ]);
  const current = validateObserverEnvelope(
    raw,
    snapshot,
    scope,
    "interfaces",
    0,
    0,
    0,
  );
  const result = buildNetworkEventsModel({
    snapshot,
    scope,
    kind: "interfaces",
    current,
    previous: null,
    now: 1,
  });
  expect(result.rates).toHaveLength(2);
  expect(result.rates.map((r) => r.txPackets).sort((a, b) => a! - b!)).toEqual([
    10, 20,
  ]);
});
