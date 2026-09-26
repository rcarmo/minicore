# Behavioral coverage map

Generated from `.feature` files by `make coverage-update`. Do not edit by hand.

Implemented scenarios execute via `make acceptance`: Behave for Python contracts and real transport; Playwright-BDD for browser interactions and host-tool contracts. Host-tool tests substitute a recording Docker executable, never a healthy network. Browser tests use a disposable loopback service, not persisted lab state.

`external` scenarios need real lab containers and an explicit collector; `planned` scenarios preserve unimplemented design requirements. Neither is counted as passing acceptance. Unit tests complement these scenarios; scenario counts are not line/branch coverage.

| Feature | Status | Runner | Expanded cases |
|---|---|---|---|
| [Present bounded live node observations without inferring routing health](../../features/diagnostics/current_live_inspector.feature) | implemented | python | 3 |
| [Current MCP results distinguish declared inventory from unavailable execution](../../features/diagnostics/current_tools.feature) | implemented | python | 9 |
| [Collect real router routes through restricted SSH and MCP](../../features/diagnostics/live_routes.feature) | external | live lab | 9 |
| [Execute only fixed God scenarios with durable recovery state](../../features/incidents/current_controller.feature) | implemented | python | 21 |
| [Apply bounded inventoried node and link faults through God-only commands](../../features/incidents/targeted_faults.feature) | implemented | python | 21 |
| [Serve MCP, assets and factual APIs on one authenticated listener](../../features/integration/current_http.feature) | implemented | python | 22 |
| [Run the initial management and MCP container](../../features/integration/initial_management.feature) | implemented | browser | 2 |
| [Inspect real node startup logs from the running lab](../../features/integration/live_node_logs.feature) | external | live lab | 1 |
| [Exercise the published Compose endpoint with an independent MCP SDK](../../features/integration/mcp_independent_client.feature) | external | live lab | 1 |
| [Verify MCP transport with independent clients and hostile wire inputs](../../features/integration/mcp_protocol.feature) | implemented | python | 25 |
| [Discover current host counter mappings for inventory data interfaces](../../features/observer/current_host_observer.feature) | implemented | python | 12 |
| [Limit live capture to inventoried IGMP control messages](../../features/observer/current_igmp_capture.feature) | implemented | python | 15 |
| [Decode bounded recent IGMP signalling from Ethernet IPv4 frames](../../features/observer/current_igmp.feature) | implemented | python | 20 |
| [Retain only bounded recent observer records in memory](../../features/observer/current_memory.feature) | implemented | python | 16 |
| [Serve shared volatile observer data through HTTP MCP and SSE](../../features/observer/current_observer_api.feature) | implemented | python | 12 |
| [Share volatile source collection through a bounded Unix socket](../../features/observer/current_observer_service.feature) | implemented | python | 12 |
| [Generate and manage the declared containers from the host only](../../features/operations/current_host_tools.feature) | implemented | host | 23 |
| [Collect bounded container evidence without service-side Docker access](../../features/operations/current_log_collector.feature) | implemented | host | 7 |
| [Inject and reset each real lab fault through God MCP](../../features/operations/live_faults.feature) | external | live lab | 1 |
| [Prove routed data-path isolation independently of baseline reachability](../../features/operations/live_isolation.feature) | external | live lab | 3 |
| [Verify read-only observer host sources against the local lab](../../features/operations/live_observer.feature) | external | live lab | 11 |
| [Measure local release resources without inferring capacity guarantees](../../features/operations/live_performance.feature) | external | browser | 1 |
| [Recover actual fixed faults after process interruption](../../features/operations/live_recovery.feature) | external | live lab | 9 |
| [Verify actual God-targeted node link and random faults](../../features/operations/live_targeted.feature) | external | live lab | 7 |
| [Walk through real faults with separate God and Operator browser views](../../features/operations/live_walkthrough.feature) | external | browser | 4 |
| [Wait for fresh log evidence after a restart invalidation](../../features/operations/log_smoke.feature) | implemented | python | 3 |
| [Boot real network nodes and observe live logs](../../features/operations/node_boot.feature) | external | live lab | 4 |
| [Issue bounded diagnostic commands in Operator mode](../../features/planned/diagnostics/operator_commands.feature) | planned | not bound | 15 |
| [Control predefined lab faults in God mode](../../features/planned/incidents/god_fault_control.feature) | planned | not bound | 23 |
| [Expose Minicore through one application service](../../features/planned/integration/unified_service.feature) | planned | not bound | 5 |
| [Observe bounded IGMP signalling without application inspection](../../features/planned/observer/igmp_observer.feature) | planned | not bound | 24 |
| [Observe topology and routing through inventory-bound read-only sources](../../features/planned/observer/routing_observer.feature) | planned | not bound | 19 |
| [Bound observer data to sixty seconds and keep the event loop responsive](../../features/planned/observer/volatile_async_lifecycle.feature) | planned | not bound | 19 |
| [Manage known lab containers from the host](../../features/planned/operations/container_lifecycle.feature) | planned | not bound | 9 |
| [Audit MCP capability decisions and fault mutations](../../features/planned/operations/mcp_audit.feature) | planned | not bound | 3 |
| [Forward customer packets through a plain IP provider network](../../features/planned/routing/provider_and_customer.feature) | planned | not bound | 6 |
| [Enforce Operator and God capability modes](../../features/planned/security/mcp_capability_modes.feature) | planned | not bound | 17 |
| [Restrict node-side execution independently of MCP](../../features/planned/security/node_dispatcher.feature) | planned | not bound | 10 |
| [One representation drives containers and the network view](../../features/planned/topology/declarative_model.feature) | planned | not bound | 13 |
| [Highlight nodes accessed by an agent with a synthwave halo](../../features/planned/visualization/agent_activity_halo.feature) | planned | not bound | 23 |
| [Show observed fault symptoms without leaking controller ground truth](../../features/planned/visualization/fault_observations.feature) | planned | not bound | 13 |
| [Switch between agent-visible evidence and full lab visibility](../../features/planned/visualization/god_visibility_toggle.feature) | planned | not bound | 19 |
| [Browse bounded evidence for a selected network node](../../features/planned/visualization/node_evidence_browser.feature) | planned | not bound | 13 |
| [Stream real node container logs without container control in the viewer](../../features/planned/visualization/node_log_streaming.feature) | planned | not bound | 24 |
| [Show exact-prefix visibility and peer-specific announcement evidence](../../features/planned/visualization/prefix_visibility.feature) | planned | not bound | 18 |
| [Distinguish routing sessions from physical data links](../../features/planned/visualization/protocol_relationships.feature) | planned | not bound | 12 |
| [Visualise routing domains without changing the data topology](../../features/planned/visualization/routing_domains.feature) | planned | not bound | 6 |
| [Compare bounded routing samples with explicit provenance and freshness](../../features/planned/visualization/routing_freshness_comparison.feature) | planned | not bound | 8 |
| [Reconcile periodic snapshots and topology notifications](../../features/planned/visualization/topology_updates.feature) | planned | not bound | 6 |
| [Keep MCP and web responsive while filesystem operations are slow](../../features/security/async_file_io.feature) | implemented | python | 19 |
| [Bound authentication work before credential reload](../../features/security/auth_admission.feature) | implemented | python | 6 |
| [Keep configured credentials out of evidence during rotation](../../features/security/credential_redaction.feature) | implemented | python | 12 |
| [Current service access and input boundaries](../../features/security/current_access.feature) | implemented | python | 29 |
| [Correlate bounded authorization and fixed mutation audit records](../../features/security/current_audit.feature) | implemented | python | 2 |
| [Isolate MCP execution and cancellation between callers](../../features/security/mcp_execution_isolation.feature) | implemented | python | 12 |
| [Validate node requests independently of the MCP client](../../features/security/node_dispatch.feature) | implemented | python | 35 |
| [Bound SSH execution and reject misleading node results](../../features/security/ssh_failure_handling.feature) | implemented | python | 16 |
| [Release transport resources for disconnected and slow clients](../../features/security/stream_resources.feature) | implemented | python | 5 |
| [Select an authorised visibility projection without changing capability](../../features/security/visibility_projection.feature) | implemented | python | 19 |
| [Combine declared topology and timestamped container presence](../../features/topology/current_state.feature) | implemented | python | 17 |
| [Cross-browser accessible evidence workbench](../../features/visualization/browser_matrix.feature) | implemented | browser | 6 |
| [Read the declared configuration file tree for a node](../../features/visualization/configuration_browser.feature) | implemented | python | 16 |
| [Publish bounded ordinary agent request activity](../../features/visualization/current_activity.feature) | implemented | python | 14 |
| [Bounded and truthful node log pages](../../features/visualization/current_log_pages.feature) | implemented | python | 26 |
| [Volatile network events panel](../../features/visualization/current_network_events.feature) | implemented | browser | 13 |
| [Distinguish declared domains and live exact-prefix evidence](../../features/visualization/current_routing_layers.feature) | implemented | python | 17 |
| [Bounded topology and node-log invalidation streams](../../features/visualization/current_streams.feature) | implemented | python | 6 |
| [Current network workbench interactions](../../features/visualization/current_workbench.feature) | implemented | browser | 41 |

## Present bounded live node observations without inferring routing health
Source: [features/diagnostics/current_live_inspector.feature](../../features/diagnostics/current_live_inspector.feature) · runner: python

- L6: Collect real interface and protocol sources for one selected router (1 case)
- L11: Failed interface collection is not reported as every link down (1 case)
- L17: Unknown node inspection cannot execute a command (1 case)

## Current MCP results distinguish declared inventory from unavailable execution
Source: [features/diagnostics/current_tools.feature](../../features/diagnostics/current_tools.feature) · runner: python

- L6: Inventory reports the full expected lab without invented observations (1 case)
- L12: God can read the fixed catalogue without activating a fault (1 case)
- L17: Unconnected execution backends return native tool failures (7 cases)

## Execute only fixed God scenarios with durable recovery state
Source: [features/incidents/current_controller.feature](../../features/incidents/current_controller.feature) · runner: python

- L7: Apply one fixed scenario and replay the request idempotently (1 case)
- L13: Reset verifies baseline before advancing generation (1 case)
- L19: Application failure rolls back without claiming success (1 case)
- L25: Baseline verification failure blocks new mutation (1 case)
- L31: Restart cannot infer baseline from a missing in-memory record (1 case)
- L37: Serialize simultaneous mutation requests (1 case)
- L41: Controller state persistence failure prevents execution (1 case)
- L46: Audit never contains credentials or arbitrary caller parameters (1 case)
- L51: Reset at verified baseline does not mutate unnecessarily (1 case)
- L56: Reject malformed persisted state without losing recovery access (1 case)
- L61: Do not advertise a new generation when reset persistence fails (1 case)
- L67: Restart never labels loaded active state as currently verified (1 case)
- L72: Recover conservatively when reset state reaches disk but generation publication fails (1 case)
- L78: Failed baseline result persistence cannot create an in-memory successful retry (1 case)
- L83: Missing generation publication is unverified even if baseline state survived (1 case)
- L89: Slow durable controller writes leave the event loop responsive (1 case)
- L93: Cancelled apply intent drains its file write before releasing the lock (1 case)
- L97: Cancellation during final reset persistence commits the verified outcome once (1 case)
- L101: A worker writes an immutable controller snapshot (1 case)
- L105: Published controller state never exposes uncommitted reset success (1 case)
- L109: Cancellation preserves a selected dice intent without rerolling (1 case)

## Apply bounded inventoried node and link faults through God-only commands
Source: [features/incidents/targeted_faults.feature](../../features/incidents/targeted_faults.feature) · runner: python

- L7: Stop an entire selected node without accepting a container name (1 case)
- L12: Disable the selected data link without stopping either node (1 case)
- L16: Persist dice selection so retries cannot reroll (1 case)
- L20: Reject unauthorized or unsafe browser mutation requests (6 cases)
- L32: Browser reset shares the controller lock and generation (1 case)
- L36: Host socket rejects unknown operations and caller-controlled arguments (1 case)
- L40: Private dice intents never enter published controller state (1 case)
- L44: Host reset does not start a node it did not stop (1 case)
- L48: Reject a foreign netem instead of adopting or deleting it (1 case)
- L52: Record host ownership before a mutation and retain it until reset verifies (1 case)
- L56: Host collection waits for all output chunks within its combined limit (1 case)
- L60: Routing corruption takes precedence and has a distinct owned protocol (1 case)
- L64: Read the node tc JSON time representation correctly (1 case)
- L68: An evicted dice result cannot execute again from a retained intent (1 case)
- L72: Malformed persisted target intents fail closed on restart (1 case)
- L76: Invalid UTF-8 browser input is rejected without node execution (1 case)

## Serve MCP, assets and factual APIs on one authenticated listener
Source: [features/integration/current_http.feature](../../features/integration/current_http.feature) · runner: python

- L6: Serve only the expected read-only HTTP routes (15 cases)
- L27: Package and serve actual production assets with security headers (1 case)
- L32: Initialize and isolate sessions on the actual HTTP transport (1 case)
- L39: Authenticate every MCP HTTP method (3 cases)
- L49: Enforce Origin policy on the actual listener (1 case)
- L54: Preserve log query parameters through the HTTP transport (1 case)

## Run the initial management and MCP container
Source: [features/integration/initial_management.feature](../../features/integration/initial_management.feature) · runner: browser

- L4: Display the complete declared network (1 case)
- L11: Expose real MCP without claiming live diagnostics (1 case)

## Verify MCP transport with independent clients and hostile wire inputs
Source: [features/integration/mcp_protocol.feature](../../features/integration/mcp_protocol.feature) · runner: python

- L3: Negotiate a supported protocol and preserve session state (2 cases)
- L11: Reject unsupported follow-up versions without corrupting a session (1 case)
- L15: Validate protocol fallback during initialization (1 case)
- L19: Process protocol ping without calling a network node (1 case)
- L23: Reject malformed JSON-RPC requests with stable errors (8 cases)
- L37: Reject ambiguous framing and unsuitable content (7 cases)
- L50: Expire and recreate an in-memory session (1 case)
- L54: Invalidate sessions on server restart (1 case)
- L58: Reconnect MCP event streaming without replay guarantees (1 case)
- L62: Rotate credentials through a service restart (1 case)
- L66: Accept combined list-valued Accept headers without weakening singleton validation (1 case)

## Discover current host counter mappings for inventory data interfaces
Source: [features/observer/current_host_observer.feature](../../features/observer/current_host_observer.feature) · runner: python

- L4: Map inventory endpoints to host peers and translate host counters (1 case)
- L11: Report typed node failures without blocking healthy nodes (1 case)
- L18: Discover Compose-prefixed network identities on the actual lab (1 case)
- L23: A netlink failure cannot become a successful empty or zero counter dump (5 cases)
- L35: Missing interface statistics are unavailable rather than zero traffic (1 case)
- L41: A replaced container cannot silently reuse another node identity (1 case)
- L47: One missing container cannot hide other inventoried nodes (1 case)
- L53: Read endpoint mapping on BusyBox without JSON ip support (1 case)

## Limit live capture to inventoried IGMP control messages
Source: [features/observer/current_igmp_capture.feature](../../features/observer/current_igmp_capture.feature) · runner: python

- L3: Kernel filter accepts only sender-side untagged IPv4 IGMP (7 cases)
- L16: Missing capture permission fails closed (1 case)
- L20: Decode an IGMP report and discard the packet bytes (1 case)
- L25: Incomplete capture cannot create a signalling event (3 cases)
- L35: Replacing a mapped interface closes its previous packet descriptor (1 case)
- L40: Lock the IGMP filter before activating bridge-level reception (1 case)
- L44: An IGMP storm is bounded without persisting packets (1 case)

## Decode bounded recent IGMP signalling from Ethernet IPv4 frames
Source: [features/observer/current_igmp.feature](../../features/observer/current_igmp.feature) · runner: python

- L3: Expose an explicit bounded IGMP frame decoder (1 case)
- L7: Decode supported bounded IGMP messages (7 cases)
- L21: Decode valid IGMP Ethernet padding variants (3 cases)
- L31: Reject malformed or unsupported bounded inputs (9 cases)

## Retain only bounded recent observer records in memory
Source: [features/observer/current_memory.feature](../../features/observer/current_memory.feature) · runner: python

- L3: Expire records and delta baselines at exactly sixty seconds (1 case)
- L8: Receipt of delayed IPC does not renew acquisition age (1 case)
- L13: Hard memory and record bounds evict oldest complete records (1 case)
- L18: Stop restart or scope identity change cannot replay prior observations (1 case)
- L23: Responses have an independent byte limit and never refresh retention (1 case)
- L29: Reject caller data outside the observer schema (1 case)
- L34: Share single-flight sources across concurrent readers (1 case)
- L39: A stalled source cannot block a healthy source or loop timers (1 case)
- L45: Parsed IGMP fields fit the volatile schema without raw packet retention (1 case)
- L50: An in-flight old generation cannot repopulate a reset observer (1 case)
- L55: A retained host sample from before reset cannot enter the new generation (1 case)
- L60: Source recovery cannot compare across a failed observation (1 case)
- L65: Multicast group cardinality is bounded independently of record count (1 case)
- L70: A silent collector cannot keep source health live indefinitely (1 case)
- L75: Loss counters belong only to the affected observation scope (1 case)
- L80: Repeated errors cannot extend the age of earlier loss counts (1 case)

## Serve shared volatile observer data through HTTP MCP and SSE
Source: [features/observer/current_observer_api.feature](../../features/observer/current_observer_api.feature) · runner: python

- L7: HTTP and Operator MCP read the same cached node scope (1 case)
- L12: Reject unbounded observer selectors before collection (5 cases)
- L23: Expired records are never served after failed refresh (1 case)
- L27: Observer invalidations contain no observation body or replay (1 case)
- L31: A generation change discards the cached observer window (1 case)
- L35: Link reads reuse node samples without counting receiver copies (1 case)
- L40: A link source failure is explicit instead of zero traffic (1 case)
- L46: A partial link response names the unavailable endpoint (1 case)

## Share volatile source collection through a bounded Unix socket
Source: [features/observer/current_observer_service.feature](../../features/observer/current_observer_service.feature) · runner: python

- L3: Read a node through a memory-only host socket (1 case)
- L8: Reject arbitrary socket targets without executing discovery (1 case)
- L13: A delayed host sample expires at acquisition time (1 case)
- L18: An observer service never widens access for a wrong Unix peer (1 case)
- L23: Routing collection strips raw fields and keeps exact routing sources (1 case)
- L28: Cancel runtime collection on service shutdown (1 case)
- L32: A slow host reader cannot stall a different node's refresh schedule (1 case)
- L36: Transfer decoded IGMP without refreshing its acquisition time (1 case)
- L42: A replacement capture interface clears its previous reports immediately (1 case)
- L46: IGMP read failure cannot leave a healthy IGMP status (1 case)
- L50: Routing comparison identity follows the mapped container incarnation (1 case)
- L54: Retained IGMP reports preserve their source failure on import (1 case)

## Generate and manage the declared containers from the host only
Source: [features/operations/current_host_tools.feature](../../features/operations/current_host_tools.feature) · runner: host

- L6: Generate byte-identical deployment artifacts (1 case)
- L14: Validate inventory before generating deployment artifacts (5 cases)
- L26: Resolve lifecycle actions only against inventory (4 cases)
- L37: Reject unsafe lifecycle requests before Docker runs (2 cases)
- L46: Collect safe presence data and select node-scoped status (1 case)
- L52: Create credentials once without revealing or overwriting them (1 case)
- L58: Enforce specification lifecycle and runner classification (1 case)
- L61: Reject a misleading acceptance report (1 case)
- L64: Use the reviewed plain-IP router image for normal inventory-bound startup (1 case)
- L69: Start an inventoried node without the obsolete investigation flag (1 case)
- L74: Keep fault SSH keys outside management mounts (1 case)
- L78: Preserve data and management separation in generated deployment (1 case)
- L82: Build dependencies resolve through exact release version locks (1 case)
- L86: Management observer memory cannot spill through swap or core dumps (1 case)
- L89: Counter-only and IGMP services cannot replace each other's active socket (1 case)

## Collect bounded container evidence without service-side Docker access
Source: [features/operations/current_log_collector.feature](../../features/operations/current_log_collector.feature) · runner: host

- L6: Redact node output before persistence (1 case)
- L9: Assign stable event identity and bound retained evidence (1 case)
- L12: Terminate bounded command execution (1 case)
- L15: Bound individual messages and the collection time window (1 case)
- L18: Collect declared nodes only with fixed log requests (1 case)
- L25: Reject an unknown selected node before collection (1 case)
- L30: Refuse overlapping host collectors (1 case)

## Wait for fresh log evidence after a restart invalidation
Source: [features/operations/log_smoke.feature](../../features/operations/log_smoke.feature) · runner: python

- L3: A log change can precede source recovery (1 case)
- L7: Persistent source failure cannot pass the log smoke (1 case)
- L11: Invalid evidence is not treated as a transient restart gap (1 case)

## Keep MCP and web responsive while filesystem operations are slow
Source: [features/security/async_file_io.feature](../../features/security/async_file_io.feature) · runner: python

- L6: Slow file reads do not stop event loop timers (5 cases)
- L18: A topology read cannot publish a previous generation after reset (1 case)
- L22: Bounded file workers retain their slots until cancelled I/O drains (1 case)
- L26: File worker admission has a hard upper bound (1 case)
- L30: A slow file read leaves independent wire MCP and HTTP requests responsive (1 case)
- L34: SSH credential metadata checks cannot block the async adapter (1 case)
- L38: Host fault ownership fsync cannot block its event loop (1 case)
- L42: Saturated file readers return a typed HTTP error (1 case)
- L46: Topology and log SSE generators do not block on file reads (1 case)
- L50: Cancel queued file work before it reaches an executor thread (1 case)
- L55: Repeated queued cancellations keep executor backlog bounded (1 case)
- L59: Cancelling file shutdown still drains running work (1 case)
- L63: Topology reads stop retrying when generations keep changing (3 cases)

## Bound authentication work before credential reload
Source: [features/security/auth_admission.feature](../../features/security/auth_admission.feature) · runner: python

- L3: Slow credential reload admits at most 32 callers (1 case)
- L10: Wire clients distinguish authentication capacity from invalid credentials (2 cases)
- L19: Existing evidence streams fail closed when authentication is busy (1 case)
- L24: In-process MCP dispatch reports authentication saturation (2 cases)

## Keep configured credentials out of evidence during rotation
Source: [features/security/credential_redaction.feature](../../features/security/credential_redaction.feature) · runner: python

- L7: Revoked credentials remain redacted from retained evidence (4 cases)
- L18: Rotation during evidence collection cannot expose a newly configured token (2 cases)
- L27: Redaction memory has a fixed fail-closed budget (2 cases)
- L37: Invalid reload does not erase retired-secret redaction (1 case)
- L41: Exhausted redaction publishes only unavailable log metadata on SSE (1 case)
- L46: Cancelling a drained reload cannot discard credential changes (2 cases)

## Current service access and input boundaries
Source: [features/security/current_access.feature](../../features/security/current_access.feature) · runner: python

- L6: Discover exactly the role-specific tools (2 cases)
- L15: Deny a guessed God tool before executing it (4 cases)
- L26: Reject unsafe diagnostic parameters (11 cases)
- L43: Authentication fails closed for unsupported identity (5 cases)
- L54: Anonymous access requires the explicit private profile (1 case)
- L60: Reject unsafe credential configuration at startup (5 cases)
- L71: Browser Basic authentication grants only Operator (1 case)

## Correlate bounded authorization and fixed mutation audit records
Source: [features/security/current_audit.feature](../../features/security/current_audit.feature) · runner: python

- L7: Correlate a successful fixed mutation and durable controller result (1 case)
- L12: Audit validation failure without logging arbitrary caller arguments (1 case)

## Isolate MCP execution and cancellation between callers
Source: [features/security/mcp_execution_isolation.feature](../../features/security/mcp_execution_isolation.feature) · runner: python

- L3: Check every role against every advertised tool (1 case)
- L8: Keep client-supplied role and session fields from escalating privilege (1 case)
- L12: Session ownership applies to all session HTTP methods (1 case)
- L16: Cancel only a request owned by the same authenticated session (1 case)
- L21: Cancel only a request owned by the same principal (1 case)
- L26: A progress token is not a cancellation target (1 case)
- L31: Reject concurrent duplicate request IDs within one scope (1 case)
- L36: Cancelling from a different session cannot affect an active call (1 case)
- L41: Deny stateless cancellation across unrelated HTTP connections (1 case)
- L46: Reject wrong-typed identities without an authorization-hook exception (1 case)
- L50: Credential rotation ends an existing MCP event stream without a restart (1 case)
- L55: Denied escalation has a bounded correlated transport audit (1 case)

## Validate node requests independently of the MCP client
Source: [features/security/node_dispatch.feature](../../features/security/node_dispatch.feature) · runner: python

- L3: Compile an exact-prefix route read into fixed executable arguments (1 case)
- L7: Reject unsafe node-side payloads (9 cases)
- L22: Distinguish malformed FRR output from an empty RIB (1 case)
- L26: A successful missing-prefix response is empty evidence (1 case)
- L30: End node execution at its own deadline (1 case)
- L34: Bound node stdout and stderr independently of the caller (1 case)
- L38: Validate the deployed dispatcher entrypoint before building images (1 case)
- L42: Preserve protocol-disabled state separately from no neighbors (1 case)
- L46: Reject unsafe fault execution independently of MCP (5 cases)
- L57: Restrict fault requests to fixed data interfaces (1 case)
- L62: Reject JSON with the wrong operation shape (7 cases)
- L75: Preserve valid empty and down observations without inferring failure (5 cases)
- L86: Preserve a no-route probe as unavailable rather than fabricated packet loss (1 case)

## Bound SSH execution and reject misleading node results
Source: [features/security/ssh_failure_handling.feature](../../features/security/ssh_failure_handling.feature) · runner: python

- L6: Classify SSH and node failures without stale success (10 cases)
- L22: Bound combined standard output and error rather than each stream separately (1 case)
- L26: Cancel and reap the local SSH process tree (1 case)
- L32: Reap descendants even after the SSH parent exits (1 case)
- L37: Enforce per-node and global concurrency without returning cached results (1 case)
- L42: A failed collection cannot reuse an earlier successful result (1 case)
- L46: Pin connection policy and reject arbitrary identity input (1 case)

## Release transport resources for disconnected and slow clients
Source: [features/security/stream_resources.feature](../../features/security/stream_resources.feature) · runner: python

- L3: A disconnected event consumer releases its stream (2 cases)
- L11: Backpressure cannot pin an event writer indefinitely (2 cases)
- L19: A vanished POST caller does not retain diagnostic execution indefinitely (1 case)

## Select an authorised visibility projection without changing capability
Source: [features/security/visibility_projection.feature](../../features/security/visibility_projection.feature) · runner: python

- L6: Operator discovery includes bounded browser evidence (1 case)
- L10: HTTP evidence matches the Operator MCP contract (3 cases)
- L20: Enforce full visibility on the server (7 cases)
- L35: No controller is not the same as no active fault (1 case)
- L39: God browser Basic credentials are authenticated without being copied to frontend state (1 case)
- L44: Authorise full-view SSE independently of snapshot reads (1 case)
- L50: Evidence selectors cannot become arbitrary paths or commands (1 case)
- L54: Revocation ends an existing evidence stream before its next event (3 cases)
- L64: Invalid credential replacement fails closed without anonymous fallback (1 case)

## Combine declared topology and timestamped container presence
Source: [features/topology/current_state.feature](../../features/topology/current_state.feature) · runner: python

- L6: Render all declared nodes and links with no observation file (1 case)
- L13: Distinguish container presence from routing health (1 case)
- L21: Reject unusable observation data without losing expected topology (8 cases)
- L38: Validate the model before serving it (7 cases)

## Cross-browser accessible evidence workbench
Source: [features/visualization/browser_matrix.feature](../../features/visualization/browser_matrix.feature) · runner: browser

- L3: Inspect nodes and routing with or without a graphics context (1 case)
- L6: Clear privileged content independently in two browser tabs (1 case)
- L9: Reject obsolete prefix requests on every browser engine (1 case)
- L12: Keep header controls grouped and reachable on tablets (1 case)
- L15: Network events remain read-only across browser engines (1 case)
- L18: Paused network events expire across browser engines (1 case)

## Read the declared configuration file tree for a node
Source: [features/visualization/configuration_browser.feature](../../features/visualization/configuration_browser.feature) · runner: python

- L7: Browse the small node-specific file tree (2 cases)
- L16: Read a known configuration file (3 cases)
- L26: Reject configuration browsing escapes and writes (6 cases)
- L38: Report unreadable or unsafe declared files honestly (3 cases)
- L48: Redact configuration secrets before exposing file contents (1 case)
- L53: Remove private key bodies as well as their configuration delimiters (1 case)

## Publish bounded ordinary agent request activity
Source: [features/visualization/current_activity.feature](../../features/visualization/current_activity.feature) · runner: python

- L6: Start and finish actual node request activity (1 case)
- L11: Preserve overlap without duplicate active counts (1 case)
- L15: Close activity on every execution outcome (3 cases)
- L24: Exclude non-node-agent access (6 cases)
- L36: Reconcile streams and enforce authentication (1 case)
- L41: Reset stale request state on generation or service epoch changes (1 case)
- L45: Bound and expire abandoned activity without an unlimited history (1 case)

## Bounded and truthful node log pages
Source: [features/visualization/current_log_pages.feature](../../features/visualization/current_log_pages.feature) · runner: python

- L6: Successful empty logs are not a collection failure (1 case)
- L11: Page older entries and expire stale cursors (1 case)
- L18: Represent log source failures explicitly (13 cases)
- L38: Reject unsafe log HTTP queries (9 cases)
- L53: Defensively redact secret-bearing messages before returning evidence (1 case)
- L60: Bound encoded responses even with long messages (1 case)

## Volatile network events panel
Source: [features/visualization/current_network_events.feature](../../features/visualization/current_network_events.feature) · runner: browser

- L3: Validate bounded observer projection and expiry without topology integration (1 case)
- L7: Export a standalone network events panel for later parent integration (1 case)
- L11: Rates use source seconds and preserve changes across the whole current window (1 case)
- L14: Malformed lifetime metadata cannot keep an observer row alive (1 case)
- L17: Incomplete observations cannot generate a withdrawal or a traffic rate (1 case)
- L20: Open live events in a compact panel and inspect without applying faults (1 case)
- L23: Pausing the list does not extend a row lifetime (1 case)
- L26: Ignore an obsolete node response after selecting a link (1 case)
- L29: Link rates match each endpoint with its own previous sample (1 case)
- L32: Repeated fetches cannot renew a record lifetime (1 case)
- L35: Conflicting record identities are rejected before rendering (1 case)
- L38: Show which link endpoint is unavailable (1 case)
- L41: A failed endpoint does not erase the healthy endpoint's rate (1 case)

## Distinguish declared domains and live exact-prefix evidence
Source: [features/visualization/current_routing_layers.feature](../../features/visualization/current_routing_layers.feature) · runner: python

- L6: Expose declared domain membership without inventing sessions (1 case)
- L11: Collect one bounded prefix snapshot through the shared evidence reader (1 case)
- L18: Do not infer receipt or policy rejection from an export (1 case)
- L24: Preserve collection failures rather than converting them to absent routes (1 case)
- L30: Deny unbounded or arbitrary routing targets (3 cases)
- L39: The node collector validates peer export targets independently (1 case)
- L43: Filter exact prefixes while retaining all observed ECMP entries (1 case)
- L49: Reject malformed routing output instead of manufacturing absence (1 case)
- L54: Reject declared metadata spoofing from node output (1 case)
- L60: Never derive absence or presence from malformed evidence (5 cases)
- L73: Reject a mixed generation routing collection (1 case)

## Bounded topology and node-log invalidation streams
Source: [features/visualization/current_streams.feature](../../features/visualization/current_streams.feature) · runner: python

- L6: Notify a topology revision change and reconnect without replay (1 case)
- L13: Notify log changes without exposing log text in the event (1 case)
- L19: Share the subscriber cap across both stream types (2 cases)
- L29: Validate streaming response framing (1 case)
- L34: Emit real authenticated log events before connection closure (1 case)

## Current network workbench interactions
Source: [features/visualization/current_workbench.feature](../../features/visualization/current_workbench.feature) · runner: browser

- L6: Inspect the full graph and an unavailable node source (1 case)
- L9: Use node and link lists when WebGL is unavailable (1 case)
- L12: Keep selection during tablet-sized periodic reconciliation (1 case)
- L15: Follow and pause log evidence without rendering executable markup (1 case)
- L18: Poll independently of the log event transport (1 case)
- L21: Discard delayed evidence from the previous node (1 case)
- L24: Camera controls do not change declared topology (1 case)
- L27: Reject malformed API data at the browser boundary (1 case)
- L30: Separate unavailable evidence tabs from functioning logs (1 case)
- L33: Reconcile topology invalidations and periodic polls without racing (1 case)
- L36: Browse a selected node's configuration file tree (1 case)
- L39: Render untrusted configuration as text and discard obsolete node responses (1 case)
- L42: Load permitted route evidence in the Routing inspector (1 case)
- L45: Render the requested synthwave halo from activity rather than node health (1 case)
- L48: Honor reduced motion for the agent-access ring (1 case)
- L51: Switch God visibility without granting a role or retaining privileged content (1 case)
- L54: Deny unavailable God access and ignore obsolete privileged responses (1 case)
- L57: Explore domains and one-prefix visibility without moving the network (1 case)
- L60: Routing evidence ages and preserves conflicting endpoint observations (1 case)
- L63: A prefix change cancels the previous routing projection (1 case)
- L66: Compare only two complete fresh routing samples within one scope (1 case)
- L69: Routing comparison is reset with its generation (1 case)
- L72: Logical session graph labels agree with endpoint tables (1 case)
- L75: God projection stays local to one tab and is cleared on revocation (1 case)
- L78: Unsafe routing samples cannot drive comparison or graph health (5 cases)
- L88: Repeated routing layer switches stay bounded at tablet size (1 case)
- L91: Changed declared peer metadata invalidates existing routing facts (1 case)
- L94: Protocol observations never obscure network nodes (1 case)
- L97: Floating diagnostics preserve a usable three-dimensional topology (1 case)
- L100: God fault modes act on exactly one selected node or link (1 case)
- L103: Live interface and summary inspectors refresh without reselection (1 case)
- L106: Routing panels refresh automatically and pause collection when minimized (1 case)
- L109: Automatic routing refresh recovers after a 503 without manual collection (1 case)
- L112: Inspector wording is short and specific (1 case)
- L115: One compact toolbar groups navigation and fault controls (1 case)
- L118: Older logs can interrupt an in-flight follow refresh (1 case)
- L121: A restored generation leaves the God toolbar usable (1 case)
