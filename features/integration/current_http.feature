@implemented @python @http
Feature: Serve MCP, assets and factual APIs on one authenticated listener
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario Outline: Serve only the expected read-only HTTP routes
    When "<role>" requests "<method>" "<path>"
    Then the HTTP status is <status>
    Examples:
      | role      | method | path                                  | status |
      | anonymous | GET    | /healthz                              | 200    |
      | operator  | GET    | /                                     | 200    |
      | operator  | GET    | /assets/main.js                       | 200    |
      | operator  | GET    | /assets/styles.css                    | 200    |
      | operator  | GET    | /api/v1/topology                      | 200    |
      | operator  | GET    | /api/v1/nodes/p1                      | 200    |
      | operator  | GET    | /api/v1/nodes/alien                   | 404    |
      | operator  | GET    | /assets/../../secrets/mcp-tokens.json  | 404    |
      | operator  | GET    | /assets/main.js.map                   | 404    |
      | operator  | POST   | /api/v1/apply_fault                   | 405    |
      | operator  | GET    | /api/v1/topology?mode=god             | 400    |
      | anonymous | GET    | /                                     | 401    |
      | anonymous | GET    | /api/v1/events                        | 401    |
      | anonymous | GET    | /api/v1/nodes/p1/logs                 | 401    |
      | anonymous | GET    | /api/v1/nodes/p1/logs/events          | 401    |

  Scenario: Package and serve actual production assets with security headers
    When "operator" requests "GET" "/"
    Then the HTML loads only the generated local application assets
    And the response has no-sniff and restrictive script and frame policies

  Scenario: Initialize and isolate sessions on the actual HTTP transport
    Given a local authenticated HTTP service is running
    When an Operator and a God client initialize sessions
    Then each client discovers only its permitted tools
    And an Operator cannot reuse a God session
    And deleting a session makes subsequent use fail

  Scenario Outline: Authenticate every MCP HTTP method
    Given a local authenticated HTTP service is running
    When a caller sends an unauthenticated "<method>" MCP request
    Then the wire status is 401
    Examples:
      | method |
      | POST   |
      | GET    |
      | DELETE |

  Scenario: Enforce Origin policy on the actual listener
    Given a local authenticated HTTP service is running
    When a caller sends an unapproved Origin header
    Then the wire status is 403

  Scenario: Preserve log query parameters through the HTTP transport
    Given a local authenticated HTTP service is running
    When an Operator sends an excessive log limit over HTTP
    Then the wire status is 400
