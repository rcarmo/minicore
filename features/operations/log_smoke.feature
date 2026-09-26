@implemented @python
Feature: Wait for fresh log evidence after a restart invalidation
  Scenario: A log change can precede source recovery
    When the log smoke sees a restart invalidation before a fresh page
    Then it waits for fresh bounded evidence and closes its connections

  Scenario: Persistent source failure cannot pass the log smoke
    When the log smoke receives unavailable pages until its deadline
    Then it fails within the deadline and closes its connections

  Scenario: Invalid evidence is not treated as a transient restart gap
    When the log smoke receives a malformed snapshot error
    Then it rejects that page without retrying
