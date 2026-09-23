@implemented @python @sse
Feature: Bounded topology and node-log invalidation streams
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario: Notify a topology revision change and reconnect without replay
    Given a topology stream is open
    When container observations change
    Then the stream emits topology.changed with the new revision
    And closing it releases its slot
    And reconnecting starts with topology.snapshot rather than replay

  Scenario: Notify log changes without exposing log text in the event
    Given current node log entries and a log stream
    When the node log snapshot changes
    Then the stream emits logs.changed without message contents
    And closing it releases its slot

  Scenario Outline: Share the subscriber cap across both stream types
    Given sixteen active streams
    When "operator" requests "GET" "<path>"
    Then the HTTP status is 503
    And the HTTP error code is stream_limit
    Examples:
      | path                         |
      | /api/v1/events               |
      | /api/v1/nodes/p1/logs/events  |

  Scenario: Validate streaming response framing
    When auxiliary response headers conflict with transport framing
    Then the response validator rejects them
    And streamed bodies cannot also have a buffered body

  Scenario: Emit real authenticated log events before connection closure
    Given a local authenticated HTTP service is running
    When an Operator opens a node log SSE stream
    Then logs.snapshot arrives before EOF without length or chunked framing
