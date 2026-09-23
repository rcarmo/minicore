@security @audit
Feature: Audit MCP capability decisions and fault mutations
  As the lab owner
  I want bounded correlated audit records
  So that privileged actions can be reconstructed without exposing secrets

  Scenario: Record a God-mode mutation
    Given an authenticated God principal requests a predefined fault
    When the request completes or fails
    Then one correlated audit trail records UTC time, audit subject, effective mode, request ID, idempotency key, tool, validated scenario parameters, lab generation, authorization decision, outcome, duration, and stable error code
    And it records rollback or reset verification when applicable
    But it does not record credentials, private keys, bearer tokens, or unrestricted environment data

  Scenario: Record a denied Operator escalation
    Given an authenticated Operator invokes a God-only tool
    When authorization denies the call
    Then the audit trail records the subject, effective Operator mode, requested tool, denial, request ID, and unchanged lab generation
    And no fault-controller event exists for that request

  Scenario: Keep privileged audit data out of ordinary evidence
    Given God-mode audit records exist
    When an Operator uses MCP or a customer uses the web UI
    Then those records and fault ground truth are not returned
    And factual topology and node evidence remain available according to their own policy
