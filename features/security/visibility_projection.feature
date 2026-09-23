@implemented @python @visibility
Feature: Select an authorised visibility projection without changing capability
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario: Operator discovery includes bounded browser evidence
    When "operator" requests tool discovery
    Then get_evidence exposes only topology, logs, declared configuration and bounded routing selectors

  Scenario Outline: HTTP evidence matches the Operator MCP contract
    Given generated node baseline files are available
    When an Operator requests "<kind>" evidence over MCP and HTTP
    Then both surfaces return the same permitted data and failure state
    Examples:
      | kind          |
      | topology      |
      | logs          |
      | configuration |

  Scenario Outline: Enforce full visibility on the server
    Given a controller state fixture containing an injected fault and a secret field
    When "<role>" requests "GET" "<path>"
    Then the HTTP status is <status>
    And "<visibility>" controller visibility is returned
    Examples:
      | role      | path                            | status | visibility |
      | operator  | /api/v1/topology                 | 200    | no         |
      | god       | /api/v1/topology                 | 200    | no         |
      | god       | /api/v1/topology?view=agent      | 200    | no         |
      | god       | /api/v1/topology?view=god        | 200    | bounded    |
      | operator  | /api/v1/topology?view=god        | 403    | no         |
      | anonymous | /api/v1/topology?view=god        | 401    | no         |
      | god       | /api/v1/topology?view=god&view=agent | 400 | no         |

  Scenario: No controller is not the same as no active fault
    When "god" requests "GET" "/api/v1/topology?view=god"
    Then the controller projection reports unavailable rather than baseline

  Scenario: God browser Basic credentials are authenticated without being copied to frontend state
    When valid God Basic credentials are supplied
    Then the principal has God capability and the capability response exposes no credential
    And incorrect God Basic credentials are denied

  Scenario: Authorise full-view SSE independently of snapshot reads
    Given a controller state fixture containing an injected fault and a secret field
    When Operator and God request full-view topology streams
    Then Operator is denied and God receives metadata-only invalidation
    And opening the God stream does not change subsequent Operator snapshots

  Scenario: Evidence selectors cannot become arbitrary paths or commands
    When an Operator supplies undocumented evidence fields or unsafe filenames
    Then each call is rejected without exposing host or controller state

  Scenario Outline: Revocation ends an existing evidence stream before its next event
    When an authenticated "<path>" stream is opened and its credential is removed
    Then the existing stream closes without another evidence event and releases its slot
    And the removed credential cannot open another evidence stream
    Examples:
      | path                         |
      | /api/v1/events?view=god      |
      | /api/v1/nodes/p1/logs/events |
      | /api/v1/activity/events     |

  Scenario: Invalid credential replacement fails closed without anonymous fallback
    When a private service credential file becomes invalid after startup
    Then both the old credential and anonymous access are rejected
