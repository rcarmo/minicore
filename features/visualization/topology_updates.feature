Feature: Keep the customer topology view current
  As a customer viewing the Minicore network
  I want the graph to reconcile periodic snapshots with live events
  So that I see recent observed state without treating a transient stream failure as network failure

  Background:
    Given the declarative inventory defines the expected topology
    And runtime observations are exposed through a versioned topology API

  Scenario: Load the initial topology
    When the customer opens the topology view
    Then the UI requests a complete topology snapshot
    And it renders expected nodes and links
    And it overlays available runtime observations
    And it displays the observation collection time and freshness

  Scenario: Receive an ordered topology event
    Given the UI has loaded topology revision 12
    And the SSE stream is connected from revision 12
    When the server emits a valid event producing revision 13
    Then the UI applies the factual state change
    And unchanged nodes retain stable positions
    And the UI records revision 13 as current

  Scenario: Reconcile state periodically
    Given the SSE stream is connected
    When the polling interval elapses
    Then the UI requests a complete topology snapshot
    And the snapshot remains authoritative over locally accumulated events

  Scenario: Recover from an interrupted event stream
    Given the UI has a previously loaded snapshot
    When the SSE connection is interrupted
    Then the existing graph remains visible
    And the UI identifies live updates as disconnected
    And the UI reconnects with bounded backoff
    And periodic snapshot polling continues

  Scenario: Detect an unrecoverable revision gap
    Given the UI cannot apply the next event in order
    When the event revision cannot be reconciled
    Then the UI requests a complete topology snapshot
    And it does not infer that any node or link is unhealthy

  Scenario: Keep diagnosis outside Minicore
    When a node or link changes observed state
    Then the UI displays the observed state
    And it labels only measured network state
    And it does not display operator fault ground truth
