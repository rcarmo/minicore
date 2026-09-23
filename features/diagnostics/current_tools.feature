@implemented @python @tools
Feature: Current MCP results distinguish declared inventory from unavailable execution
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario: Inventory reports the full expected lab without invented observations
    When "operator" calls "list_nodes" with arguments "{}"
    Then the tool succeeds with eight expected nodes
    And structured and text evidence are identical
    And every result carries correlation and generation metadata

  Scenario: God can read the fixed catalogue without activating a fault
    When "god" calls "list_fault_scenarios" with arguments "{}"
    Then the three named scenarios are reported as unavailable
    And the topology generation remains unchanged

  Scenario Outline: Unconnected execution backends return native tool failures
    When "<role>" calls "<tool>" with arguments '<arguments>'
    Then the native MCP result is an error with "backend_not_configured"
    And structured and text evidence are identical
    And every result carries correlation and generation metadata
    And the topology generation remains unchanged
    Examples:
      | role     | tool           | arguments                                                                |
      | operator | get_interfaces | {"node_id":"p1"}                                                          |
      | operator | get_routes     | {"node_id":"p1","prefix":"10.200.8.0/29"}                                |
      | operator | get_neighbors  | {"node_id":"p1","protocol":"bgp"}                                        |
      | operator | ping           | {"node_id":"p1","destination":"10.200.1.3","count":5}                     |
      | god      | get_fault_state| {}                                                                       |
      | god      | apply_fault    | {"scenario_id":"core-link-failure","idempotency_key":"acceptance-test"} |
      | god      | reset_lab      | {"idempotency_key":"acceptance-test"}                                    |
