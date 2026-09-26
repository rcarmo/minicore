@implemented @python @routing-observer @igmp
Feature: Limit live capture to inventoried IGMP control messages
  Scenario Outline: Kernel filter accepts only sender-side untagged IPv4 IGMP
    When the IGMP kernel filter sees "<frame>" from "<direction>"
    Then its capture verdict is "<verdict>"
    Examples:
      | frame          | direction | verdict |
      | valid IGMP     | incoming  | accept  |
      | valid IGMP     | outgoing  | reject  |
      | TCP            | incoming  | reject  |
      | UDP            | incoming  | reject  |
      | OSPF           | incoming  | reject  |
      | VLAN IGMP      | incoming  | reject  |
      | short ethernet | incoming  | reject  |

  Scenario: Missing capture permission fails closed
    When packet socket creation is denied by the kernel
    Then capture remains unavailable without enabling an unfiltered socket

  Scenario: Decode an IGMP report and discard the packet bytes
    Given a mapped IGMP capture source with a volatile store
    When a valid sender-side report reaches the callback
    Then only typed IGMP fields and source interface identity are retained

  Scenario Outline: Incomplete capture cannot create a signalling event
    Given a mapped IGMP capture source with a volatile store
    When capture reports "<condition>"
    Then no report record is stored and an input error counter increases
    Examples:
      | condition         |
      | checksum partial  |
      | truncated capture |
      | old kernel queue  |

  Scenario: Replacing a mapped interface closes its previous packet descriptor
    Given a mapped IGMP capture source with a volatile store
    When an interface incarnation changes or disappears
    Then old capture descriptors are closed and no old source event is published

  Scenario: Lock the IGMP filter before activating bridge-level reception
    When an inventoried packet socket is configured
    Then its locked IGMP filter precedes link-layer binding and receive buffers are bounded

  Scenario: An IGMP storm is bounded without persisting packets
    Given a mapped IGMP capture source with a volatile store
    When more than 1024 valid reports arrive within one second
    Then the remaining reports are dropped and the store record and byte bounds hold

  Scenario Outline: A wall-clock step invalidates queued capture timestamps
    Given a mapped IGMP capture source with a volatile store
    When the capture wall clock steps "<direction>" while a frame is queued
    Then queued frames are discarded and the source becomes unavailable
    And a rebound source accepts fresh reports without extending old record age
    Examples:
      | direction |
      | forward   |
      | backward  |

  Scenario: Kernel timestamps determine record age before callback processing
    Given a mapped IGMP capture source with a volatile store
    When the callback receives a frame queued for seventy seconds with stable clocks
    Then no report record is stored and an input error counter increases

  Scenario: Callback processing cannot extend a kernel timestamp lifetime
    Given a mapped IGMP capture source with a volatile store
    When the monotonic clock advances between timestamp validation and ingestion
    Then the retained report uses the original acquisition timestamp
