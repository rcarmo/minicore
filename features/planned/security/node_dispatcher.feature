@planned

@security @ssh
Feature: Restrict node-side execution independently of MCP
  Scenario: Enforce diagnostic account restrictions
    Given the service connects with its diagnostic identity and pinned host key
    When a node request reaches the forced-command dispatcher
    Then only a fixed allow-listed operation can execute
    And arguments are validated independently of the MCP service
    And the account cannot edit FRR configuration, its dispatcher or its authorized-key policy
    And PTY, port forwarding, agent forwarding and uncontrolled environment settings are disabled

  Scenario: Keep fault credentials separate
    Given the service has separate diagnostic and fault identities
    When an Operator invokes an observational command
    Then only the diagnostic identity is used
    And the fault dispatcher is not contacted

  Scenario Outline: Bound execution failure
    Given a node operation encounters <failure>
    When the operation completes or reaches its deadline
    Then it returns a stable error with correlated bounded evidence
    And it does not silently return healthy empty data
    And no local SSH process remains after cancellation or timeout

    Examples:
      | failure |
      | changed host key |
      | invalid node credentials |
      | connection timeout |
      | execution timeout |
      | malformed FRR output |
      | more than 64 KiB output |
      | caller cancellation |
      | exhausted per-node concurrency |
