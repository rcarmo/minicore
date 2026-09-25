# Fixed God fault controller

The controller exposes three fixed reversible scenarios and permits only one active fault at a time:

- `core-link-failure`: p1 `to-p2` administratively down
- `customer-bgp-failure`: ce1 `to-pe1` administratively down
- `data-path-degradation`: ce1 `to-host1` egress `tc netem` handle `1234:`, 100 ms delay, 10% requested loss

Only God MCP and God-authorised browser projection can read or mutate controller state. Operator and Agent view do not receive controller ground truth. Browser mutation controls are defined in [god-fault-toolbar.md](god-fault-toolbar.md).

## Execution boundary

The separate fault SSH key is root, forced-command-only and bound to `/usr/local/bin/minicore-fault` through a fixed `fault_authorized_keys` file. Password login, PTY and forwarding are disabled. This permits only the fixed protocol inside inventoried router containers. It does not grant arbitrary shell or host access. The diagnostic identity remains UID 11001 and cannot edit configuration. Management stays non-root and capability-free. It uses a distinct read-only fault-client key mount for controller traffic and still has no Docker socket.

Fault input accepts only `operation=fault`, a known scenario and `action=apply|reset`. Each scenario fixes its own node and interface. `tc` reset removes only handle `1234:`. Foreign qdiscs are not replaced. Interface state and qdisc presence are verified locally. Source identity, target and schema checks run independently of MCP. The key is never copied into HTTP or UI payloads.

## Durability and recovery

State, audit and idempotency records are atomically replaced and fsynced in a UID 10001-owned `/control` volume. Retention is bounded to 128 audit and result records. Retries outside that retained window are not guaranteed idempotent.

Apply verifies baseline first, records `applying`, executes the fixed change, verifies it, then records `active`. Replaying the same idempotency key with the same payload replays the same result. A changed payload returns `idempotency_conflict`. Concurrent mutations return `mutation_in_progress`. A second active scenario returns `fault_conflict`. Failed verification attempts rollback and report failure. Uncertain state blocks further applies.

Reset removes owned effects, verifies BGP peer counts and states, ten Full OSPF endpoint observations, and bidirectional sourced endpoint probes, then persists the new generation before publishing it in memory. A verified baseline reset avoids unnecessary node mutation. Persistence failure or verification failure cannot report success. Non-baseline or malformed loaded state becomes `reconciliation_required` until explicit recovery.

Only `generation.json` is shared with presence and log collectors. It contains no controller ground truth. Collectors may observe the new generation after a successful reset without changing static inventory.
