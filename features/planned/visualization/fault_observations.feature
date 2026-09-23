@planned @fault-display
Feature: Show observed fault symptoms without leaking controller ground truth
  Scenario: Present a measured link and adjacency change
    Given an interface is observed operationally down
    And its OSPF adjacency is observed no longer Full
    When the observations are refreshed
    Then the data link and adjacency each show their own observed state and timestamp
    And selecting the change exposes the supporting interface and neighbour evidence
    And unrelated links retain their own states
    And Minicore labels only measured network state

  Scenario: A changed route does not prove traffic recovery
    Given a core-link symptom is visible
    And the router selected a different next hop
    But no successful post-change probe has been collected
    When the viewer inspects the change
    Then the alternative next hop is displayed as route evidence
    And traffic recovery is not asserted

  Scenario: Show customer peering and exact-prefix evidence independently
    Given a customer BGP session is observed down
    And a complete exact-prefix RIB query reports the customer prefix absent
    When the affected nodes are selected
    Then the peer and route observations remain separate facts
    And no generated business impact or remediation recommendation is displayed

  Scenario: Keep healthy routing separate from a degraded probe
    Given observed BGP and OSPF states are up
    And a bounded probe reports packet loss and increased RTT
    When the viewer inspects the probe
    Then protocol state remains up at its collection time
    And the probe shows source, destination, direction, count, measured loss and RTT
    And no specific interface is blamed from the probe alone
    And opening the view does not launch a new probe automatically

  Scenario: Collection errors do not make the network appear failed
    Given a node collector times out
    When its evidence layer refreshes
    Then the observation is labelled unavailable
    And the expected topology remains visible
    And the device is not marked operationally down from that timeout alone

  Scenario Outline: Keep ground truth outside ordinary viewer payloads
    Given a God principal has injected a known scenario
    When a viewer with God mode unchecked receives <surface>
    Then scenario labels, injection parameters, controller identity and control-state history are excluded server-side
    And factual routing, interface and node-log observations remain available under their policy
    Examples:
      | surface                        |
      | a topology snapshot            |
      | a routing observation response |
      | a node detail response         |
      | a topology SSE invalidation    |
      | a log SSE invalidation         |
      | a cached ordinary response     |

  Scenario: Do not use a visual switch to elevate privileges
    Given an Operator-only customer has opened the ordinary workbench
    When a client requests controller ground-truth annotations through a forged God checkbox request or header
    Then the request cannot grant God capability
    And no God credential is embedded in frontend assets or stored by the ordinary viewer

  Scenario: Render protocol-derived symptoms without suppressing legitimate logs
    Given a node log records a BGP session transition after fault injection
    When an Operator opens the selected node's log tab
    Then the legitimate transition and timestamp remain visible
    And the controller's scenario label and audit record are not added to the log page
