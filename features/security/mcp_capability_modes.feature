@security @mcp
Feature: Enforce Operator and God capability modes
  As the owner of the synthetic network lab
  I want MCP capabilities derived from authenticated identity
  So that observation and fault control have a simple, enforceable boundary

  Background:
    Given the MCP endpoint supports the Operator and God capability profiles
    And capability mode is derived from authenticated server-side policy

  Scenario: Operator discovers only diagnostic tools
    Given the caller is authenticated in Operator mode
    When the caller lists MCP tools
    Then the response includes list_nodes, get_interfaces, get_routes, get_neighbors, and ping
    And the response excludes list_fault_scenarios, apply_fault, get_fault_state, and reset_lab
    And the response excludes arbitrary command, shell, SSH, Docker, and configuration tools

  Scenario: God discovers diagnostic and fault tools
    Given the caller is authenticated in God mode
    When the caller lists MCP tools
    Then the response includes all Operator diagnostic tools
    And the response includes list_fault_scenarios, apply_fault, get_fault_state, and reset_lab
    But the response excludes arbitrary command, shell, SSH, Docker, and configuration tools

  Scenario: Tool calls are authorized independently of discovery
    Given the caller is authenticated in Operator mode
    When the caller invokes apply_fault by its known tool name
    Then the server denies the call with the stable error code authorization_denied
    And no fault-controller request is made
    And the lab generation and observed state are unchanged

  Scenario Outline: Client input cannot elevate capability
    Given the caller is authenticated in Operator mode
    When the caller claims God mode using <claim_location>
    Then the effective capability remains Operator
    And a God-only tool call is denied

    Examples:
      | claim_location |
      | a tool argument |
      | an HTTP header not supplied by the trusted identity boundary |
      | a query parameter |
      | MCP session metadata |
      | a forged principal name |

  Scenario: Session ID is not authorization
    Given an Operator knows an MCP session ID created by a God principal
    When the Operator presents that session ID with Operator credentials
    Then the effective capability remains Operator
    And God-only tools remain denied

  Scenario Outline: Invalid identity fails closed
    When an MCP request has <identity_problem>
    Then the request is rejected before tool execution
    And no diagnostic or fault operation is dispatched

    Examples:
      | identity_problem |
      | missing credentials in an authenticated deployment |
      | invalid credentials |
      | expired credentials |
      | an unmapped principal |
      | an ambiguous mode mapping |

  Scenario: Anonymous private development access never receives God mode
    Given the explicit private anonymous development profile is enabled
    When an anonymous caller lists MCP tools
    Then the effective capability is Operator
    And all God-only tools are excluded and denied

  Scenario: Authentication covers the full Streamable HTTP lifecycle
    Given the authenticated exposure profile is enabled
    Then authorization is enforced for POST on the MCP endpoint
    And authorization is enforced for GET on the MCP endpoint
    And authorization is enforced for DELETE on the MCP endpoint
    And there is no unauthenticated route to the same MCP backend

  Scenario: Customer UI cannot cross the God boundary
    Given a customer is using the topology web UI
    Then the UI assets contain no God credential
    And the UI exposes no fault application or reset control
    And UI API routes cannot invoke the fault controller
