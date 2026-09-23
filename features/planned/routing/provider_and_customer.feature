@planned

@network
Feature: Forward customer packets through a plain IP provider network
  Scenario: Establish the routing baseline
    Given all eight nodes have their generated baseline configurations
    When routing converges within 60 seconds
    Then the five provider links form OSPF area 0 adjacencies
    And p1, p2, pe1 and pe2 establish a four-node iBGP full mesh
    And ce1 peers with pe1 and ce2 peers with pe2 using eBGP
    And each provider core node has both customer endpoint prefixes
    And host1 and host2 exchange packets in both directions

  Scenario: Filter unapproved advertisements
    Given a customer attempts to advertise a prefix outside the two endpoint LANs
    When the provider receives the advertisement
    Then the prefix is rejected by the explicit route policy
    And the lab does not use broad redistribution to bypass the policy

  Scenario: Demonstrate data path fidelity
    Given host1 can reach host2 through the provider network
    When every intended provider forwarding path is disabled
    Then host1 cannot reach host2
    And router management remains observable
    And the host gateway, NAT and management network do not restore endpoint reachability

  Scenario Outline: Repeat each fault and recovery twice
    Given the verified routing baseline
    When God applies <scenario>
    Then routing and probe evidence show the expected measured effect
    When God resets the lab
    Then all baseline peerings, routes and bidirectional packets are verified
    When the same apply and reset sequence is repeated
    Then no additional impairment or configuration drift remains

    Examples:
      | scenario |
      | core-link-failure |
      | customer-bgp-failure |
      | data-path-degradation |
