@implemented @python @routing-observer @igmp
Feature: Decode bounded recent IGMP signalling from Ethernet IPv4 frames
  Scenario: Expose an explicit bounded IGMP frame decoder
    When the IGMP observer parser is loaded
    Then it exposes a synchronous bounded parser callable

  Scenario Outline: Decode supported bounded IGMP messages
    Given a synthetic "<message>" Ethernet IPv4 IGMP frame
    When the parser decodes the frame with verified checksums
    Then it returns the expected IGMP observation fields for "<message>"
    Examples:
      | message   |
      | v1 query  |
      | v1 report |
      | v2 query  |
      | v2 report |
      | v2 leave  |
      | v3 query  |
      | v3 report |

  Scenario Outline: Reject malformed or unsupported bounded inputs
    Given a synthetic IGMP frame with condition "<condition>"
    When the parser validates the frame
    Then it rejects the frame as "<reason>"
    Examples:
      | condition              | reason                        |
      | invalid IPv4 checksum  | invalid_ipv4_checksum         |
      | invalid IGMP checksum  | invalid_igmp_checksum         |
      | fragmented datagram    | fragmented_ipv4_datagram      |
      | truncated frame        | truncated_igmp_message        |
      | above snap length      | frame_too_large               |
      | unsupported VLAN frame | unsupported_vlan_frame        |
      | excess v3 sources      | igmp_source_limit_exceeded    |
      | checksum offload       | unsupported_checksum_offload  |
