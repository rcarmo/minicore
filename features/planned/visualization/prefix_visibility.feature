@planned @prefixes
Feature: Show exact-prefix visibility and peer-specific announcement evidence
  Scenario: Inspect one customer prefix across router tables
    Given the baseline customer prefixes are 10.200.8.0/29 and 10.200.9.0/29
    When the viewer selects 10.200.8.0/29
    Then ce1 is labelled as its declared origin
    And a six-router matrix has separate BGP, IP RIB and forwarding-entry cells
    And graph emphasis represents the same cell evidence as the matrix
    And endpoints are marked not applicable to BGP collection

  Scenario: Declared origination does not imply observed announcement
    Given ce1 has a baseline BGP network statement for the selected prefix
    And no live route or export observation exists
    When the prefix view opens
    Then the origin is labelled declared
    And advertisements and live presence are not collected

  Scenario: Present only exact-prefix evidence as exact-prefix visibility
    Given a router has only a covering aggregate or default route
    When the selected exact customer prefix is inspected
    Then the exact-prefix cell is not present after a complete successful query
    And a covering route may appear separately as lookup evidence
    And the covering route is not labelled an announcement of the exact customer prefix

  Scenario Outline: Distinguish absence from lack of evidence
    Given the selected-prefix query returns <result>
    When the router's visibility cell is displayed
    Then it is labelled <label>
    Examples:
      | result                                | label                           |
      | a complete successful query with match| present at collection time      |
      | a complete successful query without match | not present at collection time |
      | an execution failure                  | collection unavailable          |
      | no supported collection operation     | not collected                   |
      | truncated rows without a match        | partial evidence                |
      | a sample older than the freshness bound | stale observation             |

  Scenario: A selected BGP path is not automatically a forwarding entry
    Given the router reports the selected prefix as a BGP best path
    And no kernel or forwarding-table observation is available
    When the route is selected
    Then BGP best-path state is shown
    And forwarding installation is labelled not collected

  Scenario: Show alternative and equal-cost paths explicitly
    Given route evidence contains a router-selected path and alternatives
    And forwarding evidence contains multiple equal-cost next hops
    When the selected node's prefix details are opened
    Then router-provided selection flags distinguish selected and alternate paths
    And all observed equal-cost next hops are displayed together
    And the browser does not choose its own best route

  Scenario: Directional export is supported by the sender's observation
    Given pe1 reports exporting the exact prefix to p1
    And p1's import evidence is unavailable
    When the prefix view is rendered
    Then the pe1 to p1 arrow is labelled advertised by pe1
    And reception at p1 is labelled unknown
    And the arrow links to pe1's source observation and collection time

  Scenario: Preserve the import stage reported by the source
    Given a node exposes accepted peer routes but not raw received routes
    When its prefix import cell is displayed
    Then the route is labelled accepted according to that source
    And unfiltered received-route visibility is labelled not collected
    And the viewer does not change router configuration to enable collection

  Scenario: Do not reconstruct announcements from path attributes or live sessions
    Given a selected route contains an AS_PATH
    And the associated BGP sessions are established
    But no peer-specific exported or imported route evidence was collected
    When the prefix view opens
    Then AS_PATH is shown as a route attribute
    And no export or reception arrows are inferred from it
    And no end-to-end packet path is drawn from the control-plane graph

  Scenario: Do not infer route-policy rejection from an absent export
    Given a complete advertised-routes query does not contain the selected prefix
    And no explicit policy rejection evidence was collected
    When the export cell is shown
    Then it is labelled not present at collection time
    And it is not labelled filtered or rejected

  Scenario: Distinguish disappearance from an observed withdrawal event
    Given a complete prior export sample contained the selected prefix
    And a complete current export sample for the same peer no longer contains it
    When the samples are compared
    Then the change is labelled no longer advertised between the two collection times
    And it is not labelled an observed withdrawal event without an explicit withdrawal record

  Scenario: Reject a previous prefix's delayed result
    Given a query for the first customer prefix is in flight
    When the viewer selects the second customer prefix
    And the first query returns later
    Then its response cannot populate the second prefix view
    And the current prefix and scope remain visible

  Scenario: Bound the visibility view and expose incomplete scope
    Given a router returns more paths than the configured display cap
    When the prefix response is prepared
    Then path and encoded response limits are enforced
    And truncation and the number of collected routers are displayed
    And an incomplete page cannot establish absence or withdrawal
