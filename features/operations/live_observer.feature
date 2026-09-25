@external @live-observer
Feature: Verify read-only observer host sources against the local lab
  Scenario: Map all inventoried data endpoints through actual Docker and netlink identities
    When the asyncio host observer reads the running eight-node lab
    Then all eighteen data endpoints have fresh mapped counters and no management interface
    And public counter records contain no container identities or raw command output

  Scenario: Container transmit is measured at host-veth receive
    When two host interface samples bracket a bounded endpoint probe
    Then endpoint transmit and receive packet deltas increase without negative counters
