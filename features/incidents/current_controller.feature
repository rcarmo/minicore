@implemented @python @faults
Feature: Execute only fixed God scenarios with durable recovery state
  Background:
    Given an isolated management service with Operator and God credentials
    And a controller with a recording constrained node executor

  Scenario: Apply one fixed scenario and replay the request idempotently
    When God applies the core-link scenario with a fresh request key
    Then the controller verifies the fault and records active state
    And replaying the same key returns the original outcome without another mutation
    And another scenario or changed key payload is rejected while active

  Scenario: Reset verifies baseline before advancing generation
    When God applies the core-link scenario with a fresh request key
    And God resets with a different request key
    Then the fixed fault is removed and the routing baseline is verified
    And generation advances once and repeated reset is idempotent

  Scenario: Application failure rolls back without claiming success
    Given the constrained executor will fail fault verification
    When God applies the core-link scenario with a fresh request key
    Then it attempts fixed reset and records verified baseline or reconciliation_required
    And it returns an error rather than active success

  Scenario: Baseline verification failure blocks new mutation
    When God applies the core-link scenario with a fresh request key
    And reset cannot verify healthy routing
    Then reset_failed is visible and another apply is rejected
    And generation has not advanced

  Scenario: Restart cannot infer baseline from a missing in-memory record
    When God applies the core-link scenario with a fresh request key
    And the controller process restarts
    Then it loads persisted active state and requires reconciliation before a new mutation
    And fixed reset can restore a verified baseline

  Scenario: Serialize simultaneous mutation requests
    When two God mutation requests overlap
    Then only one executes and the other returns mutation_in_progress

  Scenario: Controller state persistence failure prevents execution
    Given the controller state directory is not writable
    When God applies the core-link scenario with a fresh request key
    Then the executor is not called and the controller reports persistence_failed

  Scenario: Audit never contains credentials or arbitrary caller parameters
    When God applies the core-link scenario with a fresh request key
    Then bounded audit records contain correlation, scenario, principal and outcome
    And no secret or caller command is persisted

  Scenario: Reset at verified baseline does not mutate unnecessarily
    When God resets with a different request key
    And God resets with another fresh request key at verified baseline
    Then the second reset performs no node mutation and does not advance generation

  Scenario: Reject malformed persisted state without losing recovery access
    Given a persisted controller state with a malformed audit or invalid generation
    When the controller process restarts
    Then it reports reconciliation_required with corrupt_state rather than throwing an exception

  Scenario: Do not advertise a new generation when reset persistence fails
    When God applies the core-link scenario with a fresh request key
    And final reset persistence fails after node recovery
    Then the response is an error and the publicly visible generation has not advanced
    And new mutations require reconciliation
