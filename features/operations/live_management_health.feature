@external @management-health
Feature: Detect management readiness with a bounded native HTTP probe
  Scenario Outline: Probe the actual image without trusting container process state
    Given the management image and its generated health command
    When the native probe encounters a "<listener>" loopback listener in an isolated container
    Then its result is "<result>" within the probe deadline
    And the fixture leaves no running container behind
    Examples:
      | listener    | result    |
      | healthy     | healthy   |
      | HTTP error  | unhealthy |
      | unavailable | unhealthy |
      | stalled     | unhealthy |
