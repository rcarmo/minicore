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
