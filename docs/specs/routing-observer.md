# Routing and IGMP observer

The observer feeds the workbench and bounded APIs with volatile routing state, interface counters and optional IGMP signalling.

The observer is limited to routing state, interface counters and optional IGMP signalling. It does not inspect application traffic, payloads, host processes, packet captures or exported archives.

## Scope

The observer covers inventoried data interfaces only. Management, SSH, ingress, loopback and unrelated host or container interfaces are excluded. Routing peers, prefixes and multicast groups are network state. Process names, files, sockets and payload bytes are outside scope.

Collected views:

| View | Source | Fields |
|---|---|---|
| Interfaces and links | Host and node interface sources | Admin and oper state, RX and TX packets and bytes, errors, drops, rates and change time |
| OSPF | Bounded FRR JSON readers | Router and peer IDs, interface, area, neighbour state and state changes |
| BGP | Bounded FRR JSON readers | Peer address and AS, session state and changes, selected endpoint-LAN prefix path and next hop |
| Routes | FRR RIB, BGP and kernel route readers | Exact inventoried prefix presence, selected paths and installed next hops |
| IGMP | Filtered IPv4 control-message observation | Version, type, interface, reporter or querier address, group, bounded v3 record detail |
| Source health | Observer runtime | Availability, update time, queue overflow, tap gaps and capture loss counters |

FRR remains the routing authority. The observer does not reconstruct BGP or OSPF from packet payloads. IGMP is treated as signalling only, not authoritative membership state.

## Architecture

```text
Inventory + read-only container identity discovery
               │
       host data-interface helper
       ├─ rtnetlink counters and link events
       └─ optional IGMP-only filtered sockets
               │ bounded read-only Unix socket
               ▼
Management asyncio observer coordinator ◄─ existing restricted SSH and FRR readers
               │
        volatile state, 60-second maximum
               │
       HTTP snapshots, SSE invalidation and MCP evidence
               │
         3D graph and 2D diagnostic panels
```

The host helper validates veth mapping against inventory endpoints, network identity, peer ifindex and container incarnation. It does not guess from interface names. Rebinding on restart closes old sockets before attaching replacements.

The management coordinator owns user-facing state, shares one collection schedule per scope, and keeps existing SSH semaphore limits shared with explicit diagnostics and controller baseline checks. Background collection does not create agent-activity halos.

## Bounds and retention

Python runtime paths use asyncio for sockets, subprocesses, timers, queues and cancellation. Pure validation and short parsing stay synchronous. Blocking adapters are allowed only where bounded and explicitly controlled.

Observer retention is volatile and bounded to 60 seconds maximum across helper, management and browser. Records expire by monotonic age. Re-reading, polling or reconnecting never refreshes age. Response cache headers are `no-store`. No local storage, IndexedDB, service-worker cache, download or disk archive is part of this contract.

The in-memory store admits at most 1024 retained records and at most 8 MiB of retained encoded content plus bounded container overhead. One scope snapshot returns at most 128 records and at most 64 KiB encoded response data. The observer accepts at most 128 scopes.

Interface discovery uses one-second netlink dumps bounded to 256 KiB, `docker network inspect` bounded to 64 KiB and at most two concurrent container discovery commands. Routing collection uses a five-second interval, a 30-second timeout and concurrency 2.

IGMP capture opens at most 18 taps. Each tap uses a locked IGMP-only filter, a 2048-byte frame buffer per `recvmsg`, up to 256 bytes of ancillary data per read, and at most 16 reads per readiness callback. The capture process admits at most 8 MiB total socket receive buffering across all open taps, and the service memory budget is 128 MiB. Ingest accepts at most 1024 packets per second. Distinct multicast groups retained across the 60-second window are capped at 256.

Source health becomes `collection_timeout` if no fresh interfaces or IGMP source update arrives within 3 seconds, or if no fresh routing source update arrives within 15 seconds. Overflow, parse failure, truncation, checksum-partial packets, socket loss and kernel drops remain scoped to the affected observation source.

The observer does not write packet payloads to disk or ordinary service logs. Capture and counter services disable swap and core dumps.

## API and UI contract

The main selectors are:

- `GET /api/v1/observer?scope=node&node_id=pe1&kind=routing`
- `GET /api/v1/observer?scope=link&link_id=host1-ce1&kind=interfaces`
- `GET /api/v1/observer?scope=link&link_id=host1-ce1&kind=igmp`
- `GET /api/v1/observer/events`

`get_evidence` can return observer data through strict selectors. Both HTTP and MCP expose the same bounded observations. One node or link and one kind are allowed per request. There is no global dump.

Envelope fields include lab and generation data plus `observer_epoch`, scope, `sampled_at`, `expires_at`, `window_seconds`, availability, partial or truncated flags, missed updates, source health and bounded data. Current response size is capped at 64 KiB.

The main graph stays 3D. Observer details stay in 2D panels and tables. The [network events panel](network-events-panel.md) is the current browser surface.
