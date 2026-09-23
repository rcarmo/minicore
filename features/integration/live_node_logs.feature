@external
@live-node-logs
Feature: Inspect real node startup logs from the running lab
  Scenario: Observe real FRR startup events through the node inspector
    Given p1 exists and the host log collector has recently sampled its output
    When I open p1 in the network workbench and select Logs
    Then real container-source entries are displayed
    And successful startup events are visible without capability failures
    And pausing and following preserves the selected node
