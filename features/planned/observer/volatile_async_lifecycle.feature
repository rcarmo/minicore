@planned @routing-observer @retention @asyncio
Feature: Bound observer data to sixty seconds and keep the event loop responsive
  Scenario: Expire every observation at the retention boundary
    Given counter routing IGMP and delta-baseline records with known monotonic timestamps
    When any record reaches sixty seconds of age
    Then every host coordinator API and browser read excludes that record
    And the periodic expiry task removes it without requiring a client request
    And refreshing the page or reconnecting does not renew its age

  Scenario: Store no raw packet window or traffic artifacts
    Given observer collection is enabled for the lab
    When synthetic routing and IGMP traffic runs and the observer is stopped
    Then no PCAP packet temp file payload hash traffic log snapshot file database or historical metric write exists
    And packet buffers were discarded after decoding
    And browser persistent storage and downloads contain no observer data
    And core dumps and swap-backed observer storage were disabled

  Scenario: Wall-clock changes cannot extend the memory window
    Given observations collected with a local monotonic clock
    When UTC moves backwards or forwards
    Then expiry still uses monotonic elapsed time
    And display timestamps do not reset retention timers

  Scenario: Discard old buckets conservatively
    Given one-second counter buckets straddle the sixty-second cutoff
    When the oldest bucket starts before the cutoff
    Then that entire bucket is discarded
    And no older contribution is retained by rounding the window

  Scenario: Stop restart and lab reset invalidate volatile state
    Given a populated observer window
    When the service restarts or the lab generation changes
    Then affected windows delta baselines and queued notifications are cleared
    And clients accept only the new epoch and generation
    And persistent configuration alone cannot restore old observer records

  Scenario: Slow readers never retain expired observations
    Given a browser or MCP reader stops consuming updates
    When an observation expires before the reader resumes
    Then the queued record is discarded rather than replayed
    And reconnect fetches a current snapshot
    And the connection releases its resources by the existing writer deadline

  Scenario: Counter and IGMP storms cannot expand storage without bound
    Given the configured event group source-list and byte limits are reached
    When more observations arrive
    Then queues and stores stay within their hard bounds
    And truncation overflow or missed-update counters are visible
    And incomplete comparisons are suppressed
    And no overflow is spilled to disk

  Scenario: Kernel capture loss stays separate from simulated network loss
    Given a full packet ring drops IGMP input while router counters continue updating
    When the observer publishes source health
    Then it reports the capture loss and affected time window
    And it does not classify those drops as packets lost by the simulated link

  Scenario: A delayed source cannot block healthy updates
    Given one node read stalls and another source returns promptly
    When the asynchronous collection interval runs
    Then the healthy source is published within its update budget
    And the stalled task times out without blocking the loop
    And another task for the same scope does not accumulate behind it

  Scenario: Async subprocess cancellation cleans readers and descendants
    Given an inventoried fixed read is running with open output pipes
    When collection is cancelled or its byte or time budget is exceeded
    Then its process group is terminated and reaped
    And its reader tasks descriptors and semaphore slots are released
    And no partial output becomes successful node state

  Scenario: Blocking capture APIs are isolated and bounded
    Given a selected capture library cannot expose non-blocking reads
    When that library is used by the observer
    Then its blocking calls run only in a documented bounded adapter
    And the event loop continues servicing timers and status requests
    And stop closes the capture descriptor and terminates the adapter within its deadline

  Scenario: Background observation cannot mutate or elevate management
    Given the observer helper has only its approved read and capture permissions
    When sources fail or new containers appear
    Then no configuration forwarding qdisc container-lifecycle or fault command is issued
    And no capture target is attached without inventory validation
    And the management container still has no Docker socket host network or capture capability

  Scenario: Control-plane state expires during source failure
    Given a route or peer remains in the last successful snapshot
    When all refreshes fail for sixty seconds
    Then the old row and comparison baseline are removed
    And the source displays its failure and last successful time without replaying the old row

  Scenario: Evidence is shared but never persisted by the transport
    Given the same observer scope is requested over HTTP and Operator MCP
    When current records are returned
    Then the data freshness partial and expiry fields are equivalent
    And HTTP responses disable caching
    And neither access logging nor MCP audit records the observation body

  Scenario: Helper IPC delay cannot renew expired data
    Given an observation was acquired by the helper before a stalled socket write
    When management receives it sixty seconds after acquisition
    Then the record is discarded using acquisition age and epoch
    And receipt time does not become a new observation timestamp

  Scenario: Worst-case records cannot exceed the response budget
    Given a scope contains maximum source-list ECMP group and recent-event records
    When HTTP or MCP encodes a snapshot
    Then the encoded response is at most 64 KiB
    And event results contain at most the newest 128 records
    And whole-record truncation and omitted counts are explicit
    And truncated current state cannot drive a comparison or complete membership claim

  Scenario: Slow collection cannot block the shared MCP and web listener
    Given a node read stalls while an IGMP input burst and a slow SSE client are active
    When independent clients request MCP ping and a web snapshot
    Then both requests complete within the agreed responsiveness budget
    And other SSE subscribers continue receiving current invalidations
    And source concurrency and byte limits remain enforced

  Scenario: Client cancellation does not cancel shared source tasks
    Given two clients read the same active observer scope
    When one client cancels its HTTP or MCP request
    Then its request resources are released
    And the shared collection and the other subscriber continue
    And repeated connect cancel cycles do not increase task or descriptor counts

  Scenario: Blocking request-path I/O is isolated without losing mutation ordering
    Given a credential reload or durable fault-state file operation is deliberately delayed
    When the MCP and web listener services unrelated requests
    Then the event loop remains responsive
    And cancellation cannot release a mutation lock before its file operation is reconciled
    And later reads see either the old complete state or the new complete state
