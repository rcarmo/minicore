@planned @protocols
Feature: Distinguish routing sessions from physical data links
  Scenario: Render the provider iBGP mesh as logical relationships
    Given the four provider routers declare a full iBGP mesh
    When the viewer selects the BGP view
    Then six logical provider peerings and two customer eBGP peerings are displayed
    And each peering has two separately sourced endpoint observations
    And no BGP relationships are assigned to traffic endpoints
    And the pe1 to pe2 peering is not added as a physical cable
    And the underlying topology still has nine data links

  Scenario: Distinguish adjacency counts from endpoint counts
    Given the five provider OSPF adjacencies are Full at both ends
    When the viewer opens the OSPF layer
    Then five adjacency relationships are displayed
    And the inspector identifies ten endpoint neighbour observations
    And Full and 2-Way retain their protocol-specific meanings

  Scenario Outline: Keep observation status separate from session state
    Given a routing-session observation is <condition>
    When the relationship is rendered
    Then it is labelled <label>
    And the viewer can inspect its collection time and source
    Examples:
      | condition                         | label                         |
      | successfully observed Established | observed Established          |
      | successfully observed Idle        | observed Idle                 |
      | missing a configured collector    | not collected                 |
      | an execution timeout              | collection unavailable        |
      | older than the freshness bound    | stale observation             |
      | successful but truncated          | partial observation           |

  Scenario: Preserve one-sided session evidence
    Given p1 reports a neighbour as Full
    And the peer node cannot be collected
    When the adjacency is selected
    Then p1's Full state remains visible
    And the other endpoint is labelled unavailable
    And the relationship is labelled partial instead of confirmed healthy at both ends

  Scenario: Display conflicting peer-end observations
    Given both BGP peer endpoints were collected
    And their states disagree
    When the peering is selected
    Then each endpoint state and timestamp are displayed
    And a conflict indicator replaces a single combined healthy state

  Scenario: Container presence cannot manufacture protocol evidence
    Given all router containers are running
    And no protocol observations have been collected
    When the BGP or OSPF layer is opened
    Then only expected relationships are shown
    And no relationship is declared established from container health

  Scenario: Select a relationship from graph or table
    Given the viewer is inspecting the BGP layer
    When a peering is selected by touch or keyboard
    Then its endpoint nodes, addresses, AS numbers and observed states appear in the inspector
    And its logs and declared configuration can be opened without losing the selected relationship
