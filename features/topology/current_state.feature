@implemented @python @topology
Feature: Combine declared topology and timestamped container presence
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario: Render all declared nodes and links with no observation file
    When the topology snapshot is read twice
    Then it has eight expected nodes and exactly the nine brief links
    And all routing and link states are unknown
    And the snapshots have the same revision and collection time
    And returned snapshots cannot mutate the stored graph

  Scenario: Distinguish container presence from routing health
    Given observations contain a running p1 and an exited p2
    When the topology snapshot is read twice
    Then runtime collection is partial
    And p1 is running with unknown routing state
    And p2 is exited with unavailable node state
    And all link states remain unknown

  Scenario Outline: Reject unusable observation data without losing expected topology
    Given observations are "<condition>"
    When the topology snapshot is read twice
    Then runtime collection is unavailable
    And it has eight expected nodes and exactly the nine brief links
    And all routing and link states are unknown
    Examples:
      | condition          |
      | malformed          |
      | oversized          |
      | stale              |
      | future             |
      | another lab        |
      | another generation |
      | unknown node       |
      | invalid entry      |

  Scenario Outline: Validate the model before serving it
    Given the inventory has "<defect>"
    When the Python topology model is constructed
    Then inventory validation fails
    Examples:
      | defect              |
      | duplicate node      |
      | unknown endpoint    |
      | reused interface    |
      | overlapping subnet  |
      | gateway collision   |
      | invalid interface   |
      | repeated endpoint   |
