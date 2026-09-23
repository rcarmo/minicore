@implemented @python @audit
Feature: Correlate bounded authorization and fixed mutation audit records
  Background:
    Given an isolated management service with Operator and God credentials
    And a controller with a recording constrained node executor

  Scenario: Correlate a successful fixed mutation and durable controller result
    When a God mutation with a known request ID and idempotency key is audited
    Then the completion record contains bounded identity time decision duration generation and fixed target
    And the durable controller record matches the same idempotency key without credentials

  Scenario: Audit validation failure without logging arbitrary caller arguments
    When God supplies an invalid mutation containing credential-shaped arbitrary input
    Then audit records invalid_arguments without that input or a node mutation
