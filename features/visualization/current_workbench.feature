@implemented @browser
Feature: Current network workbench interactions
  Background:
    Given the isolated browser workbench is available

  Scenario: Inspect the full graph and an unavailable node source
    Then eight graph labels render and selecting PE1 opens unavailable logs without script errors

  Scenario: Use node and link lists when WebGL is unavailable
    Then disabling WebGL still loads the full topology and permits node selection

  Scenario: Keep selection during tablet-sized periodic reconciliation
    Then tablet-sized polling preserves P1 selection without horizontal overflow

  Scenario: Follow and pause log evidence without rendering executable markup
    Then log follow, pause, new-event notification, paging and node switching preserve context and inert text

  Scenario: Poll independently of the log event transport
    Then new log rows appear by polling when SSE is unavailable

  Scenario: Discard delayed evidence from the previous node
    Then late P1 responses never populate the selected P2 inspector

  Scenario: Camera controls do not change declared topology
    Then orbit, pan, zoom and reset change only the view while all eight nodes remain present

  Scenario: Reject malformed API data at the browser boundary
    Then schema, node, link and log-page validation reject malformed data rather than rendering invented state

  Scenario: Separate unavailable evidence tabs from functioning logs
    Then Interfaces and Routing report their unavailable backend without hiding Summary or Logs

  Scenario: Reconcile topology invalidations and periodic polls without racing
    Then topology notifications and the 15-second poll fetch authoritative snapshots while preserving selection

  Scenario: Browse a selected node's configuration file tree
    Then the Configuration tab shows declared files, renders selected file text and preserves the selected node

  Scenario: Render untrusted configuration as text and discard obsolete node responses
    Then configuration markup remains inert and a delayed P1 file never appears under P2

  Scenario: Load permitted route evidence in the Routing inspector
    Then the Routing tab displays a node-scoped evidence response and does not confuse transport errors with missing routes
