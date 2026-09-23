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

  Scenario: Apply and restore a real node fault using the God toolbar
    Given separate authenticated God and Operator browser contexts on the local lab
    When God arms lightning and clicks pe1 in the main graph
    Then the pe1 container stops and the toolbar returns to Inspect
    And restoring through the toolbar restarts pe1 and clears the fault
