@external @live-targeted
Feature: Verify actual God-targeted node link and random faults
  Scenario: Stop and recover an entire inventoried router
    Given the local targeted host executor is enabled and baseline is verified
    When God zaps node pe1 through the browser command endpoint
    Then the pe1 container is stopped and Operator inspection cannot execute there
    And explicit God restore starts the container and verifies all peers and packets

  Scenario: Stop both ends of an inventoried link
    Given the local targeted host executor is enabled and baseline is verified
    When God zaps link p1-p2 through the browser command endpoint
    Then both endpoint interfaces are down while both containers keep running
    And explicit God restore starts the container and verifies all peers and packets

  Scenario: Roll and replay one reversible corruption
    Given the local targeted host executor is enabled and baseline is verified
    When God rolls dice on ce1 and retries the same browser request
    Then the same selected corruption is verified once and the request cannot be rerolled
    And explicit God restore starts the container and verifies all peers and packets

  Scenario Outline: Measure each reversible corruption rather than relying on a random selection
    Given the local targeted host executor is enabled and baseline is verified
    When the fixed host catalogue applies "<scenario>" and records actual node evidence
    Then the selected corruption has its measured effect and explicit recovery removes it
    Examples:
      | scenario                       |
      | corrupt-delay-link-host1-ce1    |
      | corrupt-loss-link-host1-ce1     |
      | corrupt-route-node-ce1          |

  Scenario: Restore only owned effects after host service restart
    Given the local targeted host executor is enabled and baseline is verified
    When God stops host1 and the host executor restarts
    Then the stopped endpoint remains owned and God restore brings back endpoint traffic
