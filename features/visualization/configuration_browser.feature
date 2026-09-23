@implemented @python @configuration
Feature: Read the declared configuration file tree for a node
  Background:
    Given an isolated management service with Operator and God credentials
    And generated node baseline files are available

  Scenario Outline: Browse the small node-specific file tree
    When "operator" requests "GET" "/api/v1/nodes/<node>/config"
    Then the configuration tree lists only "<files>" beneath "<node>"
    And the configuration response is labelled declared baseline rather than running state
    Examples:
      | node  | files                 |
      | p1    | daemons,frr.conf      |
      | host1 | network.json          |

  Scenario Outline: Read a known configuration file
    When "operator" requests "GET" "/api/v1/nodes/<node>/config/<file>"
    Then the configuration file contains "<text>" with a content revision
    And the configuration response is labelled declared baseline rather than running state
    Examples:
      | node  | file         | text             |
      | p1    | frr.conf     | router bgp 65000 |
      | p1    | daemons      | zebra=yes       |
      | host1 | network.json | 10.200.8.3      |

  Scenario Outline: Reject configuration browsing escapes and writes
    When "<role>" requests "<method>" "<path>"
    Then the HTTP status is <status>
    Examples:
      | role      | method | path                                          | status |
      | operator  | GET    | /api/v1/nodes/alien/config                     | 404    |
      | anonymous | GET    | /api/v1/nodes/p1/config                        | 401    |
      | operator  | GET    | /api/v1/nodes/p1/config/../../secrets            | 404    |
      | operator  | GET    | /api/v1/nodes/p1/config/authorized_keys         | 404    |
      | operator  | GET    | /api/v1/nodes/p1/config?path=/etc/passwd         | 400    |
      | operator  | PUT    | /api/v1/nodes/p1/config/frr.conf                | 405    |

  Scenario Outline: Report unreadable or unsafe declared files honestly
    Given the p1 baseline file is "<condition>"
    When "operator" requests "GET" "/api/v1/nodes/p1/config/frr.conf"
    Then configuration access fails with "<error>"
    Examples:
      | condition | error                      |
      | missing   | configuration_unavailable  |
      | symlink   | configuration_unavailable  |
      | oversized | configuration_too_large    |

  Scenario: Redact configuration secrets before exposing file contents
    Given the p1 baseline contains secret-bearing configuration directives
    When "operator" requests "GET" "/api/v1/nodes/p1/config/frr.conf"
    Then the configuration secret values are absent and redaction is marked

  Scenario: Remove private key bodies as well as their configuration delimiters
    Given the p1 baseline contains a multiline private key
    When "operator" requests "GET" "/api/v1/nodes/p1/config/frr.conf"
    Then no private key body or delimiter is present in the configuration response
