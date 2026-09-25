@implemented @python @routing-observer
Feature: Share volatile source collection through a bounded Unix socket
  Scenario: Read a node through a memory-only host socket
    Given a host counter service with recorded inventory mappings
    When a permitted client reads an inventoried node scope
    Then it receives typed counters and the original acquisition time with no container ID

  Scenario: Reject arbitrary socket targets without executing discovery
    Given a host counter service with recorded inventory mappings
    When clients send unknown nodes or extra command fields
    Then the host rejects every request without invoking a collector

  Scenario: A delayed host sample expires at acquisition time
    Given a host counter service with recorded inventory mappings
    When a client reads after the host sample has expired
    Then no stale counter sample reaches management

  Scenario: An observer service never widens access for a wrong Unix peer
    Given a host counter service with recorded inventory mappings
    When the Unix peer is not the permitted management identity
    Then no counter data is returned

  Scenario: Routing collection strips raw fields and keeps exact routing sources
    Given a recording bounded SSH adapter with BGP RIB FIB and neighbor replies
    When the async observer collects one router routing scope
    Then only network peer prefix and next-hop fields are stored without raw output

  Scenario: Cancel runtime collection on service shutdown
    When a management observer runtime starts and closes with no host socket
    Then it clears all tasks and samples without blocking its caller

  Scenario: A slow host reader cannot stall a different node's refresh schedule
    When one host reader stalls while another node returns immediately
    Then the healthy host node is collected repeatedly before the stalled reader finishes

  Scenario: Transfer decoded IGMP without refreshing its acquisition time
    Given a host counter service with recorded inventory mappings
    And a decoded IGMP report is present in its volatile store
    When the permitted management client reads the IGMP scope twice
    Then both reads keep the same packet acquisition time and contain only typed fields

  Scenario: A replacement capture interface clears its previous reports immediately
    When the same host observer epoch returns a new IGMP source incarnation
    Then management retains only the reports from the new incarnation

  Scenario: IGMP read failure cannot leave a healthy IGMP status
    When interfaces succeed but the IGMP source fails after a successful report
    Then interface health stays healthy and IGMP health becomes unavailable

  Scenario: Routing comparison identity follows the mapped container incarnation
    When routing collection spans a host mapping replacement
    Then the result is discarded rather than attached to the replacement router

  Scenario: Retained IGMP reports preserve their source failure on import
    When a host snapshot contains old IGMP reports but marks capture unavailable
    Then management keeps the report timestamps and source unavailable status
