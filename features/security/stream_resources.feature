@implemented @python @mcp-security
Feature: Release transport resources for disconnected and slow clients
  Scenario Outline: A disconnected event consumer releases its stream
    When an independent client disconnects from a "<transport>" event stream
    Then the stream resources are released and management remains responsive
    Examples:
      | transport |
      | auxiliary |
      | mcp       |

  Scenario Outline: Backpressure cannot pin an event writer indefinitely
    When an independent "<transport>" client stops reading a bounded event burst
    Then backpressure closes the writer within its drain deadline without blocking management
    Examples:
      | transport |
      | auxiliary |
      | mcp       |

  Scenario: A vanished POST caller does not retain diagnostic execution indefinitely
    When an independent client disconnects after submitting a delayed diagnostic
    Then the bounded diagnostic finishes and releases its activity and request registration
