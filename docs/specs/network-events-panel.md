# Network events panel

The panel uses the deployed observer described in [routing-observer.md](routing-observer.md). It displays only routing events, interface counters and IGMP signalling. There is no packet archive, flow analysis, payload inspection, PCAP export or application telemetry.

## Interaction

The header *Network events* button opens one rounded movable and minimisable floating panel while the main topology remains 3D. A scope selector chooses an inventoried node or link. Selecting a node or link in the graph updates the panel scope while it is open. Tabs are *Routing*, *Interfaces* and *IGMP*. Routing is disabled for link scope with an explicit explanation. Endpoint scope can show Interfaces and IGMP, but not fabricated BGP or OSPF state.

The panel shows:

1. Scope, tab, source health and age.
2. A 60-second sparkline. Interfaces use directional packets per second and bytes per second from matching samples. Routing and IGMP use events per time bucket.
3. A newest-first bounded event list with time, source or interface, event and short detail.
4. *Pause* and *Follow* controls for scrolling only. Collection and expiry continue while paused.

Selecting an event source highlights the corresponding node and, where relevant, its physical link in the main graph. This inspection path cannot arm or trigger fault controls.

## Event rules

- Fresh state is shown as `Peer Established`, `Interface UP` or `Route present`. Initial state is distinct from later change.
- Routing changes include `Peer state changed`, `Route added`, `Route withdrawn` and `Next hop changed`. They are derived only from adjacent complete samples in the same observer epoch, generation and source incarnation.
- Interface rows show current state, RX and TX counters and rates. Counter decrease is `Counters reset`.
- IGMP rows show `Query`, `Report`, `Leave` or `IGMPv3 report` with group and interface. Expanded rows show bounded v3 detail.
- Empty and unavailable states are explicit: `Collecting…`, `No changes in the last 60s`, `No recent IGMP reports`, `Observer unavailable` or `IGMP capture unavailable`.
- Gaps are explicit: `Collection timed out`, `Source disconnected`, `Updates dropped`, `Response incomplete`. Expiry and failed collection never invent withdrawals.

Repeated IGMP transmissions remain separate bounded events. Grouping is not part of this contract.

## Shared API contract

The browser calls `GET /api/v1/observer` with strict selectors such as `scope=node&node_id=p1&kind=interfaces` or `scope=link&link_id=p1-p2&kind=igmp`. The panel also subscribes to `GET /api/v1/observer/events` and reacts to `observer.changed` invalidation. Records include scope, incarnation, acquisition time, sampled time, remaining lifetime and validated data. Responses include `observer_epoch`, generation, source health, missed updates and truncation data. No raw stdout and no controller ground truth are exposed.

Link scope reuses cached node sources. A missing side remains explicitly unavailable. Polling is single-flight and limited to one request per second. Minimising or closing aborts in-flight requests and closes subscriptions. Generation, epoch or scope change clears current rows and ignores late responses.

The UI rejects invalid shape, duplicate scope identity, invalid time values and oversized arrays before publication. Response cap is 64 KiB. The UI keeps at most 128 raw records and 256 rendered derived rows, with explicit clipping.
