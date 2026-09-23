@planned

@god @mcp @scenario
Feature: Control predefined lab faults in God mode
  As an authorized lab controller
  I want to apply and reset predefined faults
  So that Operator clients can inspect repeatable faults without general administrative access

  Background:
    Given the caller is authenticated in God mode
    And the lab is at a verified known-good baseline
    And no fault mutation is in progress

  Scenario: List the predefined fault catalogue
    When the caller invokes list_fault_scenarios
    Then the service returns stable IDs for core-link failure, customer-BGP failure, and data-path degradation
    And each scenario declares only its typed bounded parameters
    And no implementation command, shell fragment, Docker identifier, credential, or expected diagnosis is returned

  Scenario Outline: Apply a predefined fault
    When the caller invokes apply_fault for <scenario> with valid parameters and a new idempotency key
    Then the request enters the applying state
    And the dedicated fault controller executes the fixed mapped operation
    And the server verifies the intended factual state change
    And get_fault_state reports the fault as active to the God principal
    And the audit record links request, principal, scenario, lab generation, and outcome
    But Operator mode and the customer UI do not receive fault ground truth

    Examples:
      | scenario |
      | core-link failure |
      | customer-BGP failure |
      | data-path degradation |

  Scenario: Core-link failure remains bounded
    When the caller applies the core-link failure to an approved provider link
    Then only the selected data interface is disabled
    And management reachability remains available
    And unrelated access links are not modified

  Scenario: Customer-BGP failure remains bounded
    When the caller applies the customer-BGP failure to an approved customer peering
    Then only the selected peering or access interface is disabled according to the scenario definition
    And the other customer path remains unchanged
    And no arbitrary FRR configuration is accepted

  Scenario: Data-path degradation remains bounded
    When the caller applies approved delay and loss values to an approved data interface
    Then both values are within configured scenario limits
    And the impairment applies only in the declared direction
    And management traffic is not impaired

  Scenario Outline: Reject unsafe fault input
    When the caller invokes apply_fault using <unsafe_input>
    Then the service rejects the request before mutation
    And the lab remains at the verified baseline
    And the denial is audited with a stable error code

    Examples:
      | unsafe_input |
      | an unknown scenario ID |
      | an unknown node or link |
      | a management interface |
      | an arbitrary command or script |
      | an unsupported parameter |
      | delay or loss above the configured maximum |
      | a caller-supplied Docker container name |

  Scenario: Permit only one active fault in v1
    Given a core-link failure is active
    When the caller tries to apply a different fault
    Then the service returns fault_conflict
    And the existing fault remains unchanged
    And the second fault is not partially applied

  Scenario: Replay the same successful request safely
    Given apply_fault succeeded with an idempotency key
    When the identical request is repeated with that idempotency key
    Then the server returns the original outcome
    And the controller does not apply the fault again

  Scenario: Reject changed reuse of an idempotency key
    Given apply_fault was accepted with an idempotency key
    When a different fault request reuses that key
    Then the service returns idempotency_conflict
    And no additional mutation occurs

  Scenario: Serialize concurrent mutation attempts
    Given one God-mode mutation is applying
    When another God principal requests a mutation
    Then the second request returns mutation_in_progress
    And the two operations do not overlap

  Scenario: Roll back a partially failed application
    Given the controller changes part of the lab state
    And verification of the requested fault fails
    When the application workflow handles the failure
    Then it attempts the predefined rollback
    And it verifies whether the baseline was restored
    And it reports either baseline or rollback_failed
    And it never reports the fault as active without successful verification

  Scenario: Reset an active fault
    Given a predefined fault is active
    When the caller invokes reset_lab
    Then the controller removes the fault using the scenario's fixed reset operation
    And the service verifies the declared routing and reachability baseline
    And the lab generation advances after successful verification
    And get_fault_state reports baseline

  Scenario: Reset is idempotent at baseline
    Given no fault is active and the baseline is verified
    When the caller invokes reset_lab
    Then the service reports that the lab is already at baseline
    And it makes no unnecessary mutation

  Scenario: A failed reset is not hidden
    Given a predefined fault is active
    When reset cannot restore or verify the baseline
    Then the service reports reset_failed
    And the active or uncertain control state remains visible to God mode
    And the service does not advertise a healthy baseline
    And another mutation is blocked until reconciliation

  Scenario: Reconcile control state after service restart
    Given the service restarts while a fault may be active
    When it loads durable minimal control state
    Then it verifies the observed lab state before accepting another mutation
    And it reports baseline, active, or reconciliation_required
    And it does not infer baseline from an empty in-memory state
