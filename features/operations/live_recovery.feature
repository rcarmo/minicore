@external @live-recovery
Feature: Recover actual fixed faults after process interruption
  Background:
    Given the complete local lab is healthy and the fault controller is at baseline

  Scenario: Restart the running management service with a real active fault
    When God applies a core-link fault and the management process is restarted
    Then the new process reports unverified reconciliation and blocks another apply
    And a fresh God reset restores the live lab and advances generation once

  Scenario Outline: Lose the response after a real fixed mutation
    When an isolated controller process is interrupted by "<mode>" after a real "<scenario>" mutation
    Then its new process loads reconciliation_required without verified success
    And explicit recovery restores actual peers and packets and records one new generation
    Examples:
      | mode   | scenario               |
      | crash  | core-link-failure      |
      | crash  | customer-bgp-failure   |
      | crash  | data-path-degradation  |
      | cancel | core-link-failure      |

  Scenario: A lost God apply response is reconciled by its idempotency key
    When a God TCP caller disconnects immediately after sending a fixed apply
    Then a retry with that key returns the single recorded outcome and explicit reset restores baseline

  Scenario: Wire cancellation interrupts a slow verified reset safely
    When God cancels its reset request while baseline verification is in progress
    Then the reset reports uncertainty and a new reset recovers without premature generation advancement

  Scenario: The privileged fault key cannot escape its fixed node dispatcher
    When the real fault key attempts shell configuration wrong-node unknown-scenario PTY and forwarding requests
    Then every escape is rejected without a mutation or configuration write
    And Operator evidence cannot disclose HTTP tokens or SSH private keys

  Scenario: A missing route produces a typed probe failure through real MCP
    When a customer fault removes CE1 reachability and Operator probes the far endpoint
    Then the probe reports network_unreachable without fabricated packet counts and reset recovers
