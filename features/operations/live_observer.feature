@external @live-observer
Feature: Verify read-only observer host sources against the local lab
  Scenario: Map all inventoried data endpoints through actual Docker and netlink identities
    When the asyncio host observer reads the running eight-node lab
    Then all eighteen data endpoints have fresh mapped counters and no management interface
    And public counter records contain no container identities or raw command output

  Scenario: Container transmit is measured at host-veth receive
    When two host interface samples bracket a bounded endpoint probe
    Then endpoint transmit and receive packet deltas increase without negative counters

  Scenario: Read actual shared observations through HTTP and the official MCP SDK
    When the deployed observer sources have collected router and endpoint data
    Then real HTTP node and link scopes return bounded current counters and routing sources
    And an official Operator MCP read returns the same observer contract with no raw evidence

  Scenario: No observation file is created by the host observer
    When the deployed observer sources have collected router and endpoint data
    Then the host socket directory contains only a Unix socket and the observer process cannot swap or dump core

  Scenario: Observe a real IGMP control transmission without retaining packets
    Given the IGMP-only host observer is enabled
    When an inventoried router transmits a synthetic IGMPv2 report
    Then the scoped observer API reports the group and sending interface without raw bytes
    And the observation expires after sixty seconds even when read repeatedly

  Scenario: Capture service has only the required additional capability
    Given the IGMP-only host observer is enabled
    Then the capture process is non-root with only CAP_NET_RAW and no swap or core dumps

  Scenario: The installed kernel filter rejects non-IGMP traffic before user-space parsing
    Given the IGMP-only host observer is enabled
    When a temporary identical filtered tap receives synthetic UDP OSPF and IGMP
    Then only the IGMP transmission is delivered by the kernel
