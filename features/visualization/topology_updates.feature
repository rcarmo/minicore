@initial @browser @sse
Feature: Reconcile periodic snapshots and topology notifications
  Scenario: Load authoritative expected and observed topology
    When the customer opens the network view
    Then the UI fetches a complete versioned topology snapshot
    And expected nodes and links remain visible without live observations
    And missing observations are labelled unknown

  Scenario: Invalidate rather than merge deltas
    Given a snapshot is displayed
    When SSE announces a different topology revision
    Then the UI fetches a fresh complete snapshot
    And it does not patch unverified deltas into the graph
    And camera, selected node identity and unchanged positions are preserved

  Scenario: Poll even while events are connected
    Given the topology event stream is connected
    When 15 seconds elapse
    Then the UI fetches a complete snapshot
    And the latest fetch status is displayed separately from observation freshness

  Scenario: Recover without event replay
    Given the SSE connection is interrupted
    When the connection reopens
    Then the server sends a topology.snapshot invalidation
    And the client fetches authoritative state even if it has an old event ID
    And polling continues during reconnect
    And collection failure does not imply link failure

  Scenario: Bound event consumers
    Given the service has 16 active topology streams
    When another client requests a stream
    Then it receives a stream_limit error
    And a disconnected or expired stream releases its slot

  Scenario: Keep slow browser requests from overwriting newer state
    Given a topology fetch is already in flight
    When a second refresh is requested
    Then the second request is coalesced behind the first
    And a disposed view ignores or cancels outstanding requests
