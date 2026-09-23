@implemented @python @logs
Feature: Bounded and truthful node log pages
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario: Successful empty logs are not a collection failure
    Given a successful empty node log snapshot
    When the node log page is requested
    Then its status is ok and there are no entries

  Scenario: Page older entries and expire stale cursors
    Given five valid node log entries
    When two pages of size two are requested
    Then their entries are deterministic and do not overlap
    And a cursor cannot cross nodes
    And rotating the snapshot expires its previous cursor

  Scenario Outline: Represent log source failures explicitly
    Given the log snapshot is "<condition>"
    When the node log page is requested
    Then the log error code is "<error>"
    Examples:
      | condition          | error                  |
      | missing            | backend_not_configured |
      | stopped node       | node_unavailable       |
      | timed out          | collection_timeout     |
      | command failure    | collection_failed      |
      | output cap         | output_limit           |
      | stale              | collector_stale        |
      | malformed          | invalid_log_snapshot   |
      | oversized          | invalid_log_snapshot   |
      | symlink            | invalid_log_snapshot   |
      | invalid entry      | invalid_log_snapshot   |
      | wrong node         | invalid_log_snapshot   |
      | another lab        | generation_mismatch    |
      | another generation | generation_mismatch    |

  Scenario Outline: Reject unsafe log HTTP queries
    When "operator" requests "GET" "<path>"
    Then the HTTP status is <status>
    Examples:
      | path                                                    | status |
      | /api/v1/nodes/alien/logs                                  | 404    |
      | /api/v1/nodes/p1/logs?source=audit                         | 400    |
      | /api/v1/nodes/p1/logs?path=/etc/passwd                     | 400    |
      | /api/v1/nodes/p1/logs?command=id                           | 400    |
      | /api/v1/nodes/p1/logs?limit=-1                             | 400    |
      | /api/v1/nodes/p1/logs?limit=501                            | 400    |
      | /api/v1/nodes/p1/logs?limit=2&limit=3                       | 400    |
      | /api/v1/nodes/p1/logs?cursor=invalid                       | 400    |
      | /api/v1/nodes/p1/logs/events?limit=1                       | 400    |

  Scenario: Defensively redact secret-bearing messages before returning evidence
    Given valid entries containing configured credentials and secret patterns
    When the node log page is requested
    Then recognized secrets and terminal escapes are absent
    And ordinary HTML is returned as inert message text
    And private key blocks are absent

  Scenario: Bound encoded responses even with long messages
    Given a near-limit log snapshot
    When a page of 500 entries is requested
    Then its encoded response is less than 64 KiB
    And any omitted entries have an older-page cursor
