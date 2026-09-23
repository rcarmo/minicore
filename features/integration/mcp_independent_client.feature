@external @mcp-client
Feature: Exercise the published Compose endpoint with an independent MCP SDK
  Scenario: Initialize and call tools through a published authenticated container
    Given a disposable management Compose instance with isolated Operator and God credentials
    When the official Python MCP SDK connects from the host
    Then it negotiates the actual supported protocol and lists the role-specific tools
    And the SDK session event stream attaches successfully without HTTP 400
    And it invokes all five Operator tools and receives matching structured and text evidence
    And it observes native errors for unconnected backends rather than synthetic success
    And a separate God client sees all nine tools without changing the Operator's discovery
    And deleting sessions and stopping the fixture leaves no test service or secret files behind
