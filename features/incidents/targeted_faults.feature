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

  Scenario: Host reset does not start a node it did not stop
    When the host receives reset with no owned fault journal
    Then it returns unchanged success without executing Docker

  Scenario: Reject a foreign netem instead of adopting or deleting it
    When a data interface already has an unowned netem rule
    Then targeted corruption is denied and no ownership is recorded

  Scenario: Record host ownership before a mutation and retain it until reset verifies
    When the host applies and resets a selected node with a simulated Docker executor
    Then ownership is durable before stop and removed only after verified start

  Scenario: Host collection waits for all output chunks within its combined limit
    When a host command emits its JSON in separated pipe writes
    Then the host receives the complete JSON before verifying a mutation

  Scenario: Routing corruption takes precedence and has a distinct owned protocol
    When the host compiles a customer-prefix blackhole
    Then its fixed metric wins over BGP and it is not labelled as a BGP-owned route

  Scenario: Read the node tc JSON time representation correctly
    When tc reports a nested 0.1 second delay for an owned queue
    Then the host recognises the configured 100 millisecond delay

  Scenario: An evicted dice result cannot execute again from a retained intent
    When God rolls corruption then its result expires after recovery
    Then retrying the retained intent returns idempotency_expired without a new mutation

  Scenario: Malformed persisted target intents fail closed on restart
    When the targeted intent journal is corrupted and the controller restarts
    Then targeted apply requires reconciliation and publishes no corrupt private intent

  Scenario: Invalid UTF-8 browser input is rejected without node execution
    When God submits invalid UTF-8 to the browser fault endpoint
    Then no host mutation executes and the browser request is rejected
