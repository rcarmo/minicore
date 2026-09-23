@implemented @python @activity
Feature: Publish bounded ordinary agent request activity
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario: Start and finish actual node request activity
    When an authorised node-directed MCP request begins and finishes
    Then its node is active during execution and inactive after completion
    And the activity response contains no arguments, result bodies or credentials

  Scenario: Preserve overlap without duplicate active counts
    When two ordinary requests overlap on p1
    Then finishing one retains p1 activity until the other finishes

  Scenario Outline: Close activity on every execution outcome
    When a node request ends by "<outcome>"
    Then its active record is removed without a health-state change
    Examples:
      | outcome                 |
      | backend_not_configured  |
      | exception               |
      | cancellation            |

  Scenario Outline: Exclude non-node-agent access
    When "<kind>" occurs
    Then no node activity record is published
    Examples:
      | kind                |
      | list_nodes          |
      | denied God call     |
      | invalid node        |
      | browser routes      |
      | background snapshot |
      | God mutation        |

  Scenario: Reconcile streams and enforce authentication
    When an Operator opens the activity snapshot and stream
    Then the stream begins with bounded active-state metadata and releases its slot on close
    And an unauthenticated viewer cannot read activity in the authenticated profile

  Scenario: Reset stale request state on generation or service epoch changes
    When the lab generation changes with old activity still recorded
    Then the next snapshot excludes old-generation activity

  Scenario: Bound and expire abandoned activity without an unlimited history
    When more than the activity cap is recorded and time advances past the request lease
    Then the snapshot stays bounded and abandoned active records disappear
