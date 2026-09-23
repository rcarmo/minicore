@implemented @host
Feature: Generate and manage the declared containers from the host only
  Background:
    Given a temporary copy of the host tools and canonical inventory

  Scenario: Generate byte-identical deployment artifacts
    When the canonical deployment is generated twice
    Then Compose and all FRR outputs are identical
    And only management is in the default profile with loopback publication and no privileges
    And all eight nodes map to declared services and nine separate data bridges
    And endpoint gateways point at customer routers
    And generated artifact drift fails the check command

  Scenario Outline: Validate inventory before generating deployment artifacts
    Given the generator inventory contains "<defect>"
    When the canonical deployment generation is attempted
    Then it fails without creating deployment artifacts
    Examples:
      | defect             |
      | duplicate service  |
      | unknown endpoint   |
      | invalid interface  |
      | overlapping subnet |
      | gateway collision  |

  Scenario Outline: Resolve lifecycle actions only against inventory
    Given a recording Docker executable instead of a real daemon
    When the host helper requests "<action>" for "p1" with local investigation enabled
    Then it passes fixed Compose arguments for "<action>" and p1 only
    Examples:
      | action  |
      | up      |
      | start   |
      | stop    |
      | restart |

  Scenario Outline: Reject unsafe lifecycle requests before Docker runs
    Given a recording Docker executable instead of a real daemon
    When the host helper requests "<action>" for "<node>" without local investigation
    Then it fails without calling Docker
    Examples:
      | action | node  |
      | start  | p1    |
      | up     | p1    |
      | restart| p1    |
      | stop   | alien |
      | exec   | p1    |

  Scenario: Collect safe presence data and select node-scoped status
    Given a recording Docker executable instead of a real daemon
    When the host observation helper runs
    Then the observation file contains eight logical node states and no container IDs
    And the publication leaves no temporary file behind

  Scenario: Create credentials once without revealing or overwriting them
    When the secret initialization tool runs twice
    Then distinct Operator and God credentials are stored with owner-only permissions
    And the second call fails without changing the credentials
    And neither invocation prints a credential

  Scenario: Enforce specification lifecycle and runner classification
    Then every implemented scenario has exactly one execution runner and no planned scenario can masquerade as implemented

  Scenario: Reject a misleading acceptance report
    Then a passing report with an outline renamed to another behavior fails the acceptance gate
