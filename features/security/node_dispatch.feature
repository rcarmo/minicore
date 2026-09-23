@implemented @python @dispatcher
Feature: Validate node requests independently of the MCP client
  Scenario: Compile an exact-prefix route read into fixed executable arguments
    When the node dispatcher receives a valid get_routes request for an IPv4 prefix
    Then it chooses the fixed vtysh executable and exact show route arguments without a shell

  Scenario Outline: Reject unsafe node-side payloads
    When the node dispatcher receives "<payload>"
    Then it rejects the payload before executing a process
    Examples:
      | payload               |
      | malformed JSON        |
      | unknown operation     |
      | extra field           |
      | external destination  |
      | shell syntax          |
      | excessive count       |
      | invalid protocol      |
      | oversized stdin       |
      | non-object JSON       |

  Scenario: Distinguish malformed FRR output from an empty RIB
    When an exact-prefix node command returns invalid JSON
    Then the dispatcher returns parse_failure rather than an empty healthy result

  Scenario: A successful missing-prefix response is empty evidence
    When an exact-prefix node command returns an empty JSON object
    Then the dispatcher returns successful bounded raw and normalised empty data

  Scenario: End node execution at its own deadline
    When a fixed node command exceeds its deadline
    Then the node process is killed and the response reports execution_timeout

  Scenario: Bound node stdout and stderr independently of the caller
    When a fixed node command exceeds the output cap
    Then it is terminated with output_limit rather than retaining unlimited output

  Scenario: Validate the deployed dispatcher entrypoint before building images
    When the node dispatcher source is compiled and its denied command entrypoint is invoked
    Then it produces a bounded JSON denial without a Python traceback

  Scenario: Preserve protocol-disabled state separately from no neighbors
    When an OSPF query is requested on a node without declared OSPF
    Then the dispatcher reports protocol_not_enabled without interpreting an empty response as healthy neighbors

  Scenario Outline: Reject unsafe fault execution independently of MCP
    When the node fault dispatcher receives "<request>"
    Then the fault request is rejected without running a command
    Examples:
      | request           |
      | arbitrary command |
      | unknown scenario  |
      | wrong node        |
      | extra interface   |
      | invalid action    |

  Scenario: Restrict fault requests to fixed data interfaces
    When the node fault dispatcher compiles the three approved scenarios
    Then commands address only p1 to-p2, ce1 to-pe1 and ce1 to-host1
    And no caller argument selects a management interface or executable
