@external @browser @performance
Feature: Measure local release resources without inferring capacity guarantees
  Scenario: Record browser API and container measurements under bounded evidence collection
    Then the live workbench records timing frame heap and container samples and releases browser resources
