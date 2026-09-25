# Minicore specification

Minicore is an IP network simulator for demonstrating troubleshooting techniques. It runs real FRRouting daemons and Linux forwarding in a fixed Docker Compose topology. A browser and restricted Model Context Protocol (MCP) tools expose measured network evidence. Reversible faults support repeatable diagnosis and recovery exercises.

## Scope

The simulator provides eight nodes, nine data links, IPv4 OSPF and BGP, bounded diagnostics, a 3D workbench, container logs, declared configuration and a short-lived routing/IGMP observer. It uses synthetic addresses and open-source software. It requires no proprietary router images or external network integration.

The requirements below define the simulator's contracts. The [coverage map](docs/development/behavior-coverage.md) separates executable acceptance from planned scenarios. See [known limitations](docs/operations/known-limitations.md) for operating bounds.

## Topology and routing

`inventory/topology.json` is the source of node, service, interface, address, link and position identity. `make generate` produces Compose and router configuration. The viewer must not interpret shared management-network membership as a data link.

| Nodes | Simulated role | Routing |
|---|---|---|
| `p1`, `p2` | Provider core | OSPF area 0 and provider iBGP |
| `pe1`, `pe2` | Provider edge | OSPF, provider iBGP and access eBGP |
| `ce1`, `ce2` | Access edge | eBGP and endpoint LAN advertisements |
| `host1`, `host2` | Packet endpoints | Default route through the attached CE |

Provider routers use AS 65000 and a four-node loopback-sourced iBGP full mesh. CE1 and CE2 use AS 65001 and AS 65002. PE routers use next-hop-self. Prefix filters admit only `10.200.8.0/29` and `10.200.9.0/29`; broad redistribution is prohibited. CE means Customer Edge in standard routing terminology; all nodes and prefixes are simulated.

| Data link | Network | First endpoint | Second endpoint |
|---|---|---|---|
| p1–p2 | `10.200.1.0/29` | p1 `.2` | p2 `.3` |
| pe1–p1 | `10.200.2.0/29` | pe1 `.2` | p1 `.3` |
| pe1–p2 | `10.200.3.0/29` | pe1 `.2` | p2 `.3` |
| pe2–p1 | `10.200.4.0/29` | pe2 `.2` | p1 `.3` |
| pe2–p2 | `10.200.5.0/29` | pe2 `.2` | p2 `.3` |
| ce1–pe1 | `10.200.6.0/29` | ce1 `.2` | pe1 `.3` |
| ce2–pe2 | `10.200.7.0/29` | ce2 `.2` | pe2 `.3` |
| host1–ce1 | `10.200.8.0/29` | host1 `.2` | ce1 `.3` |
| host2–ce2 | `10.200.9.0/29` | host2 `.2` | ce2 `.3` |

Each link has its own bridge. Docker reserves `.1`; endpoint default gateways use CE `.3`. Management uses `172.30.250.0/24`, gateway `.1`, management service `.2` and routers `.11`–`.16`. Loopbacks are `10.254.0.1/32` through `.6/32`. Check overlap with host and VPN routes before starting the simulator. Compose 2.36 or later supplies deterministic interface names.

Traffic must traverse the declared routers. Tests must show that disabling every provider path breaks endpoint traffic while management diagnostics remain available. Host gateways, NAT and management interfaces must not provide bypass paths. This is a cooperative local lab, not hostile-tenant containment.

## Runtime and access

One non-root Python `AsyncMCPServer` process serves MCP, HTTP assets, APIs and server-sent events (SSE) on port 9000. Compose publishes `127.0.0.1:19000`. Management has a read-only root filesystem, dropped Linux capabilities, no host networking and no Docker socket. It joins ingress and management networks, never data links. Router images use pinned FRR source and only the required capabilities; `SYS_ADMIN` and privileged containers are prohibited.

The `private` development profile permits anonymous Operator access. Invalid supplied credentials must fail closed. The `authenticated` profile requires a valid Operator credential; God always requires a distinct credential. MCP uses Bearer authentication. The browser accepts either role through HTTP Basic. Remote credential use requires TLS, source filtering and a non-bypassable authenticated ingress. Keep the default loopback binding unless an authenticated ingress and source restrictions are configured.

Use asyncio for Python sockets, subprocesses, timers, collection and shutdown. Keep pure parsers synchronous. Filesystem operations on live request paths must use bounded off-loop adapters or preloaded immutable data. Cancelling an operation must not release capacity while its worker still runs. Mutations remain serialised through durable persistence and reconciliation.

## Diagnostic tools

Roles are derived from server-authenticated identity. Filter discovery by role and authorise each call independently. Session IDs, UI controls and tool annotations grant no permissions.

| Operator tool | Evidence |
|---|---|
| `list_nodes` | Inventoried identities, roles and supported operations |
| `get_interfaces` | Declared interfaces and measured admin/oper state, addresses and counters |
| `get_routes` | FRR routes, optionally for a validated IPv4 prefix |
| `get_neighbors` | BGP peers or OSPF adjacencies, including explicit disabled/unknown states |
| `ping` | At most five ICMP packets to an inventoried data-plane destination |
| `get_evidence` | Shared browser evidence: topology, logs, declared configuration, routing and observer snapshots |

God adds `list_fault_scenarios`, `apply_fault`, `get_fault_state` and `reset_lab`. No role can execute arbitrary commands, upload scripts, select external targets, edit configuration or access unrestricted Docker control.

Diagnostic SSH uses pinned host keys and a forced-command dispatcher. The dispatcher independently validates bounded JSON from stdin and invokes fixed argument arrays. Disable PTY, forwarding, password login and uncontrolled environment settings. Keep the dispatcher and authorisation policy immutable to its account. `vtysh -u` is not a security boundary.

SSH limits are a five-second connection timeout, a 15-second operation deadline, 64 KiB combined output, two concurrent commands per node and eight globally. Cancellation must terminate and reap local subprocesses; node-side execution also has a deadline.

Results include schema version, request ID, lab ID, generation, node, operation, UTC collection time, duration, status, normalised data, bounded raw evidence, truncation and a stable error code. Missing routes are valid empty results. Loss and unreachable networks are diagnostic observations; execution or parse failures must never become healthy empty results. Keep structured and text MCP output consistent and set the outer `isError` flag for domain failures.

MCP uses Streamable HTTP at `/mcp`, supporting protocol versions `2025-03-26` and `2024-11-05`. Test initialise/discovery/calls, ping, invalid framing, GET/reconnect/DELETE, expiry, restart, role revocation and official SDK interoperability. Reconnecting streams resynchronise from snapshots; no replay is promised.

## Faults and recovery

The fixed MCP scenarios are `core-link-failure`, `customer-bgp-failure` and `data-path-degradation`. They affect the p1–p2 link, CE1–PE1 peering and CE1–host1 egress respectively. Keep controller labels and expected answers outside Operator-visible evidence. Observable routing and log transitions remain available for diagnosis.

The God browser toolbar adds inventory-bound targets:

- **Zap:** stop a selected node container or disable both ends of a selected link.
- **Corrupt:** choose one compatible fixed delay, loss or prefix-blackhole action; persist the choice before execution so retries do not reroll.
- **Restore lab:** remove owned mutations, verify baseline routing and traffic, then advance the generation.

Only one fault may be active. Serialize mutations and retain bounded durable intent, results, audit and idempotency records. Reconcile interrupted work after restart; uncertain state blocks new mutations. Restore only Minicore-owned changes. A lost response does not imply rollback.

Router faults use a separate forced-only SSH identity. Whole-node and targeted link faults use an opt-in host Unix-socket service with UID checks, a fixed inventory-derived catalogue and a private ownership journal. Management never receives the Docker socket or host capabilities. Browser mutation requires God authentication, same-origin POST JSON and an explicit intent header. Inspection never triggers a fault.

## Workbench and evidence

The main topology always stays 3D. Use 2D graphs and tables only within diagnostic panels. Panels must be movable, minimisable and scrollable, with keyboard controls, visible focus, touch targets and an accessible fallback when WebGL is unavailable. The generation remains an internal consistency field.

Show physical links, declared autonomous systems and OSPF areas separately from logical protocol sessions. Keep BGP, RIB, FIB and sender export evidence distinct. Compare only fresh, complete, same-scope samples. Collection is bounded and non-atomic; failures do not imply withdrawals. Unsupported pre-policy imports must be explicit.

The per-tab God checkbox requests an authorised projection without changing credentials. Default to Agent view; clear sensitive state on view change, revocation, reset and late responses. Ordinary agent node access produces a bounded activity halo; background collectors and fault mutations do not reveal controller activity.

Interfaces, neighbours and routes refresh while their inspectors are open. Container logs support Follow/Pause and bounded pagination. The Configuration tab shows redacted declared baselines, never uncollected running configuration. Exact HTTP routes and evidence contracts are in the [runbook](docs/operations/runbook.md), [logs](docs/specs/log-streaming.md) and [configuration browser](docs/specs/configuration-browser.md).

Host log collection writes snapshots mounted read-only into management. Retain at most 15 minutes, 500 entries and 60 KiB per node. Log pages default to 100 entries, cap at 500 and remain below 64 KiB encoded. Bind cursors to node, generation and revision. Sources older than 15 seconds report `collector_stale`. Redact credentials before persistence and again on reads; render text without executing HTML or terminal escapes.

## Routing and IGMP observer

The observer collects interface counters, bounded FRR routing state and optional IGMP signalling. It does not inspect applications, host processes or payloads. Retain observations for at most 60 seconds in volatile memory, including browser history. No PCAP archives or disk spill. Pause stops scrolling, not expiry.

Use service-owned asyncio collection with bounded work, shared reads, explicit source health and cancellation. Rebind sources after node recreation and invalidate old generation/epoch samples. Do not invent membership from missing packets. The optional non-root host capture process has only `CAP_NET_RAW`; management remains capability-free. Lock an IGMP-only kernel filter before capture. Disable swap and core dumps for capture services. See [observer contracts](docs/specs/routing-observer.md) for exact parser, queue, memory and expiry limits.

## Verification and maintenance

Every behaviour change follows Gherkin, a genuine failing behavioural test, minimal implementation, passing acceptance and a tested commit. Existing working behaviour may begin with passing characterisation. `make coverage-update` generates the coverage map; `make acceptance` checks exact implemented scenario identities and results. Planned and external cases are separate.

| Gate | Required evidence |
|---|---|
| A1 — Build | Pinned sources, packages, digests, licences and dependency inventory; no secrets in source or image layers |
| A2 — Baseline | Eight ready nodes, expected OSPF/BGP peers, exact routes, bidirectional packets and measured resources |
| A3 — Isolation | Actual packet paths and total-path failure without host/NAT/management shortcuts |
| A4 — MCP | Independent wire and official SDK checks, role filtering and matching structured/text results |
| A5 — Access | Credential and origin negatives, forced-command escape rejection and private node SSH |
| A6 — Failure handling | Deadlines, bounds, concurrency, cancellation, malformed data, unavailable sources and cleanup |
| A7 — Recovery | Repeated faults, explicit reset, replay, restart and interrupted-mutation reconciliation |
| A8 — Reproducibility | README setup, runbook, fresh-checkout acceptance and documented operating limits |

Run live mutation suites serially. Verify the recovered baseline and restore any service stopped by a test. Retain upstream licences and modification notices. Do not infer universal GPU support, remote access security or production readiness from local results.
