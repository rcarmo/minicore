@implemented @python @routing-view
Feature: Distinguish declared domains and live exact-prefix evidence
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario: Expose declared domain membership without inventing sessions
    When the topology snapshot is read twice
    Then provider routers declare AS 65000 and area 0 while endpoints have no BGP ASN
    And each logical BGP peering is distinct from the nine physical links

  Scenario: Collect one bounded prefix snapshot through the shared evidence reader
    Given six routers return controlled routing observations
    When the routing view requests 10.200.8.0/29
    Then BGP, RIB, FIB and per-peer advertisement observations remain separate
    And each node result includes source, collection time, completeness and generation
    And the same Operator MCP evidence selector returns equivalent data

  Scenario: Do not infer receipt or policy rejection from an export
    Given six routers return controlled routing observations
    When the routing view requests 10.200.8.0/29
    Then a reported advertised route has sender-side provenance only
    And raw received routes are labelled not collected

  Scenario: Preserve collection failures rather than converting them to absent routes
    Given one routing collector fails while the other five succeed
    When the routing view requests 10.200.8.0/29
    Then five observations are collected and the unavailable node retains its error
    And the response is labelled partial rather than healthy absence

  Scenario Outline: Deny unbounded or arbitrary routing targets
    When "operator" requests "GET" "<path>"
    Then the HTTP status is 400
    Examples:
      | path                                                       |
      | /api/v1/routing?prefix=0.0.0.0/0                             |
      | /api/v1/routing?prefix=10.200.8.0/29&prefix=10.200.9.0/29    |
      | /api/v1/routing?command=show-all                            |

  Scenario: The node collector validates peer export targets independently
    When a routing dispatcher receives a peer outside its declared peer list
    Then the peer export request is denied before execution

  Scenario: Filter exact prefixes while retaining all observed ECMP entries
    Given bounded FRR and kernel outputs include only a covering BGP and RIB route and two exact FIB nexthops
    When the node collects one prefix routing snapshot
    Then covering routes are not reported as exact BGP or RIB presence
    And both exact FIB nexthops remain in the evidence

  Scenario: Reject malformed routing output instead of manufacturing absence
    Given the BGP collector returns a JSON list instead of a routing object
    When the node collects one prefix routing snapshot
    Then the collection reports parse_failure instead of absent routes

  Scenario: Reject declared metadata spoofing from node output
    Given six routers return controlled routing observations
    And one node returns an unrelated prefix in the routing response
    When the routing view requests 10.200.8.0/29
    Then the unrelated prefix is rejected as parse_failure

  Scenario Outline: Never derive absence or presence from malformed evidence
    Given six routers return controlled routing observations
    And one node returns malformed "<field>" routing evidence
    When the routing view requests 10.200.8.0/29
    Then the unrelated prefix is rejected as parse_failure
    Examples:
      | field       |
      | advertised  |
      | fib         |
      | bgp         |
      | received    |
      | rib         |

  Scenario: Reject a mixed generation routing collection
    Given six routers return controlled routing observations
    And generation advances during routing collection
    When the routing view requests 10.200.8.0/29
    Then no prior generation evidence is returned as current
