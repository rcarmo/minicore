@planned @routing-observer @igmp
Feature: Observe bounded IGMP signalling without application inspection
  Scenario: Only IGMP datagrams reach the packet decoder
    Given a tap attached to a verified lab data interface
    When the interface sees application traffic BGP OSPF and IPv4 IGMP
    Then only protocol-2 datagrams reach the bounded IGMP decoder
    And neither raw packets nor application fields reach the observer records

  Scenario Outline: Decode supported membership signalling fields
    Given a valid bounded "<message>" on an inventoried interface
    When the observer decodes the datagram
    Then it emits the version type group reporter or querier and interface identity
    And it emits only bounded IGMPv3 record source addresses when present
    And it discards the datagram bytes immediately
    Examples:
      | message       |
      | v1 query      |
      | v1 report     |
      | v2 query      |
      | v2 report     |
      | v2 leave      |
      | v3 query      |
      | v3 report     |

  Scenario Outline: Reject incomplete or invalid IGMP without creating membership facts
    Given an IGMP input has condition "<condition>"
    When the decoder validates the input
    Then it emits no membership or report record from that input
    And a bounded parse or unsupported-input counter increments
    And packet bytes are absent from logs and responses
    Examples:
      | condition              |
      | invalid checksum       |
      | truncated header       |
      | inconsistent length    |
      | fragmented datagram    |
      | above snap length      |
      | excess source records  |
      | unsupported version    |
      | unsupported VLAN frame |

  Scenario: Avoid duplicate tap copies without suppressing repeated reports
    Given a known IGMP report is transmitted once and then transmitted again
    When sender and receiver host veths can both observe each transmission
    Then the sender-side direction policy emits one observation per transmission on the link
    And both real transmissions remain in the recent window
    And observations on distinct links remain separately attributed

  Scenario: Expiring a report does not invent a multicast leave
    Given a report was seen but no authoritative membership table is available
    When that report reaches sixty seconds without another report
    Then it is removed from the recent window
    And the interface displays No recent reports
    And no receiver absence or synthetic leave event is inferred

  Scenario: Present signalling and authoritative membership as different sources
    Given a leave message is observed while a fresh supported router membership table still contains the group
    When the IGMP inspector refreshes
    Then it shows Leave seen as a recent event and the independently sampled membership row
    And it does not replace the membership table with the packet-derived guess

  Scenario: Keep IGMPv3 filter semantics explicit
    Given a report contains bounded INCLUDE and EXCLUDE source-filter records
    When recent signalling is displayed
    Then record types and source addresses remain explicit
    And they are not collapsed into an unconditional joined or left state

  Scenario: Do not confuse bridge forwarding state with router membership
    Given a Linux bridge multicast database and local kernel socket memberships are readable
    When no supported router membership reader exists
    Then bridge state is labelled as bridge forwarding state if exposed
    And local socket memberships are not presented as downstream receivers
    And router membership is marked unavailable

  Scenario: Keep unicast lab behaviour unchanged without multicast configuration
    Given no IGMP messages are observed and no multicast membership source is enabled
    When the observer starts
    Then routing and link counters continue to update
    And the IGMP panel shows No recent reports and the membership capability status
    And the observer does not enable PIM snooping multicast routing or a querier

  Scenario: Untapped senders are outside recent signalling coverage
    Given an IGMP query originates on a non-inventoried host bridge interface
    When only inventoried node transmit directions are tapped
    Then the inspector states its sender-side coverage
    And it does not infer that the external querier is absent from the link

  Scenario: Validate checksum offload at the real capture boundary
    Given valid synthetic IGMP and deliberately corrupt messages on the deployed veth kernel
    When checksum offload metadata accompanies sender-side capture
    Then the tested policy distinguishes verified checksums from partial or unsupported checksums
    And an unverifiable checksum is not labelled confirmed invalid wire traffic
