@implemented @python @fault-toolbar
Feature: Apply bounded inventoried node and link faults through God-only commands
  Background:
    Given an isolated management service with Operator and God credentials
    And a targeted controller with a recording host executor

  Scenario: Stop an entire selected node without accepting a container name
    When God requests a zap of node pe1
    Then the fixed host request stops only the inventoried pe1 service
    And reset restarts it and verifies baseline before advancing generation

  Scenario: Disable the selected data link without stopping either node
    When God requests a zap of link p1-p2
    Then both link endpoints are disabled and no container stop is compiled

  Scenario: Persist dice selection so retries cannot reroll
    When God rolls corruption on node ce1 and repeats the request key
    Then one bounded corruption is executed and both responses name the same chosen fault

  Scenario Outline: Reject unauthorized or unsafe browser mutation requests
    When "<role>" submits a browser fault with "<condition>"
    Then no host mutation executes and the browser request is rejected
    Examples:
      | role     | condition           |
      | operator | valid               |
      | god      | missing origin      |
      | god      | foreign origin      |
      | god      | missing intent      |
      | god      | unknown target      |
      | god      | arbitrary argument  |

  Scenario: Browser reset shares the controller lock and generation
    When God submits a valid browser fault and resets with a new key
    Then both actions use the same audited controller and restore baseline

  Scenario: Host socket rejects unknown operations and caller-controlled arguments
    When the host receives unknown targets arbitrary commands or extra request fields
    Then all host requests are denied before Docker execution

  Scenario: Private dice intents never enter published controller state
    When God rolls corruption on node ce1 and repeats the request key
    Then published controller state excludes the durable intent map
