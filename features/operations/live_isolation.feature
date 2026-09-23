@external @live-isolation
Feature: Prove routed data-path isolation independently of baseline reachability
  Background:
    Given the complete local lab is healthy and the fault controller is at baseline

  Scenario: Data endpoints cannot enter management or host gateways
    When each endpoint probes its local management address and Docker bridge gateway
    Then all management and host gateway probes fail
    And restricted management diagnostics still succeed for every router

  Scenario: Cut every provider path without breaking management
    When packet capture observes bidirectional endpoint traffic across the provider
    Then request packets traverse CE1, PE1, a core router, PE2 and CE2 without a management hop
    When both PE1 provider interfaces are disabled temporarily
    Then endpoint traffic fails in both directions while management diagnostics succeed
    And host-gateway and management-next-hop shortcut attempts fail
    And restoring both links recovers peerings and bidirectional endpoint traffic

  Scenario: Enforce container and host ingress boundaries
    Then only management loopback port 19000 is published and routers have no default route
    And all data bridges are internal without host gateway access or masquerading
    And external diagnostic targets are denied before node execution
