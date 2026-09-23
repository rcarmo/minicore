@management-slice
Feature: Run the initial management and MCP container
  Scenario: Display the complete declared network
    Given the initial management container is ready
    When I open the network workbench
    Then I see eight nodes and nine links
    And I can select PE1 and open its log browser
    And the log browser reports that its node source is unavailable

  Scenario: Expose real MCP without claiming live diagnostics
    Given the initial management container is ready
    When an Operator initializes an MCP session
    Then discovery exposes exactly the five diagnostic tools
    And list_nodes returns all eight expected nodes
    And get_routes reports backend_not_configured as a tool error
    And reset_lab is denied before any mutation
