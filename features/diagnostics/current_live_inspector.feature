@implemented @python @inspector
Feature: Present bounded live node observations without inferring routing health
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario: Collect real interface and protocol sources for one selected router
    Given the node adapter supplies interface and neighbor observations
    When "operator" requests "GET" "/api/v1/nodes/p1/observations"
    Then the inspector response preserves independent interfaces BGP and OSPF observations with times

  Scenario: Failed interface collection is not reported as every link down
    Given the node adapter supplies interface and neighbor observations
    And interface collection times out
    When "operator" requests "GET" "/api/v1/nodes/p1/observations"
    Then the unavailable interface source is explicit while successful neighbor facts remain visible

  Scenario: Unknown node inspection cannot execute a command
    Given the node adapter supplies interface and neighbor observations
    When "operator" requests "GET" "/api/v1/nodes/management/observations"
    Then the HTTP status is 404
    And the inspector adapter has executed no requests
