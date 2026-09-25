@planned @routing-observer
Feature: Observe topology and routing through inventory-bound read-only sources
  Scenario: Discover all and only the current lab data interfaces
    Given the eight-node nine-link inventory and unrelated host networks
    When the observer discovers current interface mappings
    Then every inventoried data endpoint is mapped to a verified host veth peer
    And management ingress SSH loopback and unrelated interfaces are excluded

  Scenario: Rebind after container recreation
    Given an active observer mapping for a router data interface
    When that container is recreated with new namespace and interface identifiers
    Then the old descriptor is closed and the old incarnation is invalidated
    And collection resumes only after validating the new inventory mapping
    And no counter delta spans the two incarnations

  Scenario: Report interface direction without counting both ends twice
    Given controlled packets are sent from node A to node B over one inventoried link
    When both host veth counters are sampled
    Then A host-veth ingress is presented as A transmit and B host-veth egress as B receive
    And the A to B link transmission count uses A transmit only
    And the chart does not sum sender and receiver copies

  Scenario: Separate counter discontinuity from traffic rate
    Given two samples for one interface incarnation
    When a counter decreases or the collection interval is missing
    Then the rate is unavailable for that interval
    And no negative or inflated rate is emitted

  Scenario: Do not infer packet loss from unsynchronised interface counters
    Given the two link endpoints were sampled at different times
    When their transmit and receive counters differ
    Then both values and collection times remain visible independently
    And no calculated link loss percentage is produced

  Scenario: Use FRR state instead of parsing routing protocol packets
    Given BGP and OSPF are enabled on an inventoried router
    When the observer refreshes its peers and configured customer prefixes
    Then it uses independently validated fixed FRR and kernel readers
    And it does not open BGP or OSPF packet-analysis sessions
    And no TCP UDP application flow inventory is created

  Scenario: Preserve exact route and ECMP source semantics
    Given FRR reports two BGP paths and an installed route with two kernel next hops
    When a prefix observation is published
    Then BGP selection RIB installation and kernel next hops remain distinct
    And every returned next hop is retained within the response limit
    And a covering route is not exact-prefix presence

  Scenario: Emit a withdrawal only after a complete successful comparison
    Given an exact prefix appeared in a successful current-generation sample
    When the next complete matching sample omits that prefix
    Then a route withdrawal is emitted with previous and current observation times

  Scenario Outline: Do not manufacture route withdrawals from collection failures
    Given an exact prefix appeared in a successful current-generation sample
    When the next collection has condition "<condition>"
    Then no route withdrawal is emitted
    And the source condition is exposed independently
    Examples:
      | condition       |
      | timeout         |
      | partial         |
      | truncated       |
      | malformed       |
      | node stopped    |
      | sample expired  |
      | epoch changed   |

  Scenario: Share collection across all clients
    Given multiple browser tabs and MCP clients subscribe to the same router scope
    When one scheduled collection interval occurs
    Then at most one background collection runs for that scope
    And all readers receive its observation times and freshness
    And the existing per-node and global SSH ceilings also constrain background reads
    And the observer does not light an agent-access halo

  Scenario: Handle a stopped router as a source transition
    Given the observer is following a router
    When an authorised God action stops that node container
    Then its mapping and source availability change without a collector crash
    And the Operator record contains no injected scenario or controller journal
    And unrelated nodes continue updating

  Scenario: Bound read-only selectors before touching the host
    Given Operator and God clients can read observer records
    When a caller supplies an external target interface name capture filter retention override or arbitrary command
    Then the request is rejected before opening a source or executing a command
    And ordinary Operator and God observer results use the same projection

  Scenario: Keep simulator views readable
    Given current link counters routing peers and route changes are available
    When the user opens a routing or link inspector
    Then live values and collection times appear in the existing floating panel
    And the main graph stays three-dimensional
    And source details remain expandable without covering node controls
    And traffic display does not reuse the agent-access halo
