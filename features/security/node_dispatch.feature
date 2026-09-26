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

  Scenario Outline: Reject JSON with the wrong operation shape
    When the node normalises "<operation>" output "<output>"
    Then the operation fails parsing rather than claiming healthy empty evidence
    Examples:
      | operation      | output                                        |
      | get_routes     | []                                            |
      | get_routes     | {"10.200.8.0/29":"absent"}                  |
      | get_interfaces | {}                                            |
      | get_interfaces | ["mgmt0"]                                    |
      | get_neighbors  | []                                            |
      | ping           | 2 packets transmitted, 3 received, 0% packet loss |
      | ping           | 2 packets transmitted, 0 received, 0% packet loss |

  Scenario Outline: Preserve valid empty and down observations without inferring failure
    When the node normalises "<operation>" output "<output>"
    Then the result is the same typed evidence rather than a parse failure
    Examples:
      | operation      | output                                                              |
      | get_routes     | {}                                                                  |
      | get_interfaces | []                                                                  |
      | get_interfaces | [{"ifname":"to-p1","flags":[],"operstate":"DOWN"}]         |
      | get_neighbors  | {}                                                                  |
      | get_neighbors  | {"ipv4Unicast":{"peers":{"10.254.0.2":{"state":"Idle"}}}} |

  Scenario: Preserve a no-route probe as unavailable rather than fabricated packet loss
    When ping exits with a network unreachable diagnostic and no packet summary
    Then the node reports network_unreachable with no invented counts


  Scenario Outline: Reject malformed neighbor payloads without breaking valid disabled or idle shapes
    When the node normalises malformed neighbor case "<case>"
    Then neighbor parsing fails with parse_failure
    Examples:
      | case        |
      | BGP peers[] |
      | BGP peerbadrow |
      | OSPF string |
      | OSPF listbadrow |

  Scenario Outline: Preserve valid neighbor payload fixtures for disabled and established or idle states
    When the node normalises valid neighbor case "<case>"
    Then neighbor parsing preserves the original typed payload
    Examples:
      | case             |
      | disabled empty   |
      | BGP established  |
      | BGP idle         |
      | OSPF established |
      | OSPF wrapped |

  Scenario Outline: Reject malformed neighbor success payloads returned over SSH
    When the SSH adapter receives malformed neighbor success case "<case>"
    Then the adapter returns parse_failure with bounded raw neighbor evidence
    Examples:
      | case        |
      | BGP peers[] |
      | BGP peerbadrow |
      | OSPF string |
      | OSPF listbadrow |
