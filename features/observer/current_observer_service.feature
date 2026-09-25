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
