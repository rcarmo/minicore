@implemented @python @routing-observer
Feature: Serve shared volatile observer data through HTTP MCP and SSE
  Background:
    Given an isolated management service with Operator and God credentials
    And a populated volatile observer service

  Scenario: HTTP and Operator MCP read the same cached node scope
    When Operator reads node p1 observer interfaces through HTTP and MCP
    Then both transports return the same records without starting a collector
    And replies disable HTTP caching and exclude raw output and controller state

  Scenario Outline: Reject unbounded observer selectors before collection
    When the observer API receives "<query>"
    Then the observer request is rejected without opening a source
    Examples:
      | query                                                   |
      | scope=node&node_id=management&kind=interfaces             |
      | scope=node&node_id=p1&kind=payload                        |
      | scope=node&node_id=p1&kind=interfaces&duration=600         |
      | scope=node&node_id=p1&kind=interfaces&node_id=p2          |
      | scope=link&link_id=missing&kind=igmp                      |

  Scenario: Expired records are never served after failed refresh
    When the populated observer ages beyond sixty seconds
    Then HTTP returns an empty window instead of repeating the previous record

  Scenario: Observer invalidations contain no observation body or replay
    When the observer event stream is read and then the credential is revoked
    Then only an epoch and revision invalidation is sent and the stream releases its slot

  Scenario: A generation change discards the cached observer window
    When the lab generation changes before an observer read
    Then all previous records and baselines are invalidated before the response
