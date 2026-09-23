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

  Scenario: Render the requested synthwave halo from activity rather than node health
    Then a node activity event creates a bounded halo and accessible cue, overlap stays lit, and completion fades without changing selection

  Scenario: Honor reduced motion for the agent-access ring
    Then reduced motion uses a steady activity ring and obsolete generations never light a node

  Scenario: Switch God visibility without granting a role or retaining privileged content
    Then an authorised God checkbox reveals source-labelled controller state and unchecking it clears that state without changing node selection

  Scenario: Deny unavailable God access and ignore obsolete privileged responses
    Then an Operator cannot enable the checkbox and a late God-view response cannot overwrite Agent view

  Scenario: Explore domains and one-prefix visibility without moving the network
    Then the workbench can switch AS, OSPF, BGP and prefix layers with source labels and a six-router evidence matrix

  Scenario: Routing evidence ages and preserves conflicting endpoint observations
    Then routing evidence becomes stale and BGP endpoint disagreement is not collapsed

  Scenario: A prefix change cancels the previous routing projection
    Then a late first-prefix response cannot replace the second prefix evidence

  Scenario: Compare only two complete fresh routing samples within one scope
    Then routing comparison shows observed withdrawals but never converts a failed refresh into one

  Scenario: Routing comparison is reset with its generation
    Then a new generation clears earlier routing comparisons without moving node selection

  Scenario: Logical session graph labels agree with endpoint tables
    Then BGP and OSPF graph labels match the same endpoint facts shown in their tables

  Scenario: God projection stays local to one tab and is cleared on revocation
    Then God annotations never appear in an Agent tab and revocation clears the privileged tab

  Scenario Outline: Unsafe routing samples cannot drive comparison or graph health
    Then a "<condition>" routing sample cannot claim an observed withdrawal or healthy session
    Examples:
      | condition  |
      | partial    |
      | stale      |
      | truncated  |
      | duplicate  |
      | bad-time   |

  Scenario: Repeated routing layer switches stay bounded at tablet size
    Then keyboard and touch-sized routing controls retain selection without accumulating graph labels

  Scenario: Changed declared peer metadata invalidates existing routing facts
    Then changed peer addresses within a generation clear routing evidence until recollected
