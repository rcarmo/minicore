@external @node-boot
Feature: Boot real network nodes and observe live logs
  Scenario: Boot the complete network without blanket privileges
    When the host starts the declared lab profile
    Then all six router and two endpoint containers become healthy within 90 seconds
    And every router runs zebra, bgpd and ospfd without SYS_ADMIN or privileged mode
    And the management container still has no Docker socket or added capabilities
    And endpoint default gateways point to their CE routers

  Scenario: Verify baseline peerings and bidirectional packets
    Given all lab nodes are healthy
    Then the provider has ten Full OSPF neighbor entries and twelve established iBGP peer entries
    And both customer eBGP sessions are established on both ends
    And host1 and host2 exchange three packets in each direction

  Scenario: Observe actual logs after a node restart
    Given all lab nodes are healthy
    And the host node log collector is running
    When the host restarts p1
    Then p1 becomes healthy again
    And a real p1 log event invalidates its HTTP log page via SSE
    And the browser displays fresh node messages without startup capability failures

  Scenario: Persist automatic local collection across a collector restart
    Given all lab nodes are healthy
    When the owner enables the explicit host log watcher
    Then fresh bounded node log snapshots remain available without an interactive shell loop
    And restarting that watcher resumes collection without a stale collector lock
    And stopping that watcher makes old samples visibly stale
