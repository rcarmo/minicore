@external @browser @live-fault-ui
Feature: Walk through real faults with separate God and Operator browser views
  Scenario Outline: Show controller truth only to God while Operator collects actual evidence
    Given separate authenticated God and Operator browser contexts on the local lab
    When an official God MCP client applies "<scenario>" while both browsers observe
    Then God sees the fixed scenario and Operator sees only factual routing evidence
    And explicit SDK reset clears controller state and the browser receives the new generation
    Examples:
      | scenario              |
      | core-link-failure     |
      | customer-bgp-failure  |
      | data-path-degradation |
