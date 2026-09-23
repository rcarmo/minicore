@planned @routing-freshness
Feature: Compare bounded routing samples with explicit provenance and freshness
  Scenario: Compare two eligible samples of the same scope
    Given two complete successful routing observations have the same node, peer, prefix and generation scope
    When the viewer selects Compare previous sample
    Then changed fields and additions or removals are shown with both collection times
    And common nodes retain their positions
    And the comparison remains an observation comparison without a diagnostic conclusion

  Scenario: Wait until an eligible baseline exists
    Given only one complete successful observation of the selected scope exists
    When the routing view opens
    Then Compare previous sample is unavailable with a reason
    And the viewer does not invent a prior healthy state

  Scenario: Partial or failed collection cannot imply a withdrawn route
    Given a prior complete sample contained the selected prefix
    And the next sample is failed or truncated
    When the view refreshes
    Then the previous result remains labelled with its original time and failed or stale refresh status
    And no route removal or withdrawal is inferred from missing rows

  Scenario: Display collection skew before combining evidence
    Given one router's sample is fresh
    And another fresh sample falls outside the allowed cross-node skew window
    When both are displayed for the selected prefix
    Then their individual facts and timestamps remain visible
    And the combined view is labelled temporally inconsistent
    And no atomic network snapshot or complete propagation chain is asserted

  Scenario: Refresh on SSE while retaining periodic reconciliation
    Given a routing view is selected
    When SSE invalidates its observation revision
    Then the UI fetches a complete authoritative scoped snapshot
    And periodic polling remains active
    And camera, node, prefix, layer and inspector selection are preserved

  Scenario: Clear comparison when the lab generation changes
    Given the viewer is comparing two observations from one lab generation
    When a reset publishes a different generation
    Then prior observations cannot be merged with the new generation
    And comparison is cleared until eligible new samples are collected
    And the declared configuration view remains separately labelled

  Scenario: Keep historical comparison bounded
    Given the viewer has loaded the current and previous eligible samples
    When newer eligible samples arrive
    Then only the two samples needed for the current comparison are retained by this feature
    And no durable event archive or full history replay is required

  Scenario: Preserve accessible state distinctions
    Given routing evidence is present, absent, stale, partial or unavailable
    When the graph, table and inspector render it
    Then each state has a text or shape cue in addition to colour
    And the same evidence and timestamp can be reached with keyboard or touch
    And reduced-motion mode does not animate state transitions
