@implemented @python @sse
Feature: Reserve stream admission before transport starts consuming events
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario Outline: Unstarted responses consume their shared subscriber slots
    When sixteen "<kind>" event responses are created without reading them
    Then the next event request returns 503 stream_limit
    And closing unread and started responses releases each slot exactly once
    Examples:
      | kind     |
      | topology |
      | logs     |
      | activity |
      | observer |

  Scenario Outline: Revocation during collection suppresses the pending event
    When a "<kind>" event waits on collection while its credential is revoked
    Then it closes without emitting the pending event and releases its slot
    Examples:
      | kind     |
      | topology |
      | logs     |

  Scenario: A slow God snapshot cannot outlive its credential
    When a God topology response waits on collection while its credential is revoked
    Then the HTTP response denies access without controller state
