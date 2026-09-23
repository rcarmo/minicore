@operator @mcp
Feature: Issue bounded diagnostic commands in Operator mode
  As an Operator MCP client
  I want fixed observational commands
  So that I can collect evidence without changing the lab

  Background:
    Given the caller is authenticated in Operator mode
    And the lab inventory and diagnostic operation allow-list are loaded

  Scenario Outline: Issue an allowed diagnostic command
    When the caller invokes <tool> with valid inventory-bounded input
    Then the server executes only the fixed operation mapped to <tool>
    And the result includes request ID, lab generation, collection time, duration, status, normalized data, and bounded raw evidence
    And the operation does not change configuration, routing administration, interfaces, processes, or fault state

    Examples:
      | tool |
      | list_nodes |
      | get_interfaces |
      | get_routes |
      | get_neighbors |
      | ping |

  Scenario Outline: Reject command escape attempts
    When the caller supplies <unsafe_input> to a diagnostic tool
    Then validation fails with a stable error code
    And no shell is invoked with caller-controlled command text
    And no external or management target is contacted

    Examples:
      | unsafe_input |
      | an unknown node ID |
      | an arbitrary IP address |
      | shell metacharacters |
      | a command substitution expression |
      | an unknown interface |
      | a probe count above the maximum |
      | an unsupported routing protocol |
      | an additional undocumented argument |

  Scenario: A failed probe remains an observation
    Given an approved destination does not answer ICMP
    When the caller invokes ping
    Then the tool reports the executed probe and measured packet loss
    And it does not report a transport execution failure
    And it does not diagnose the cause

  Scenario: Failure to execute a command is explicit
    Given the node dispatcher is unavailable
    When the caller invokes an allowed diagnostic tool
    Then the tool returns a stable execution error
    And it does not return cached success or an empty healthy result
