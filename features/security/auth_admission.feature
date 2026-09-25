@implemented @python @auth-admission
Feature: Bound authentication work before credential reload
  Scenario: Slow credential reload admits at most 32 callers
    Given an isolated management service with Operator and God credentials
    When 34 HTTP callers arrive while credential reload is blocked
    Then two callers receive 503 file_io_busy without waiting for reload
    And cancelling a waiting caller releases its authentication admission
    And every remaining admitted caller authenticates after reload completes

  Scenario Outline: Wire clients distinguish authentication capacity from invalid credentials
    When an independent "<transport>" client reaches a full authentication queue
    Then it receives a temporary 503 file_io_busy response
    And a health request remains responsive and authentication recovers
    Examples:
      | transport |
      | HTTP      |
      | MCP       |

  Scenario: Existing evidence streams fail closed when authentication is busy
    Given an isolated management service with Operator and God credentials
    When an activity stream reauthenticates against exhausted file capacity
    Then the stream closes without yielding an event or leaking a slot

  Scenario Outline: In-process MCP dispatch reports authentication saturation
    Given an isolated management service with Operator and God credentials
    When "<method>" dispatch encounters exhausted authentication file capacity
    Then dispatch returns file_io_busy without an internal or credential error
    Examples:
      | method     |
      | tools/list |
      | tools/call |
