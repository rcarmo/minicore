@implemented @python @routing-observer
@observer @host-observer
Feature: Discover current host counter mappings for inventory data interfaces
  Scenario: Map inventory endpoints to host peers and translate host counters
    Given the current inventory and fixed Docker inspect and exec responses
    When the isolated Linux host observer collects interfaces
    Then each inventoried data endpoint is mapped through container and host peer indexes
    And host RX counters are exposed as container transmit and host TX as container receive
    And the observer uses only fixed inventory Docker commands and a host rtnetlink dump

  Scenario: Report typed node failures without blocking healthy nodes
    Given one node has no matching host peer while another remains healthy
    When the isolated Linux host observer collects interfaces
    Then the healthy node still returns translated interface counters
    And the failed node reports a typed discovery error
    And management and unrelated host interfaces are excluded

  Scenario: Discover Compose-prefixed network identities on the actual lab
    Given Docker uses Compose-prefixed network names with inventory labels
    When the isolated Linux host observer collects interfaces
    Then healthy data endpoints map using the actual network identities

  Scenario Outline: A netlink failure cannot become a successful empty or zero counter dump
    Given a netlink dump with "<fault>"
    When the host decodes the bounded dump
    Then it rejects the dump as incomplete or malformed
    Examples:
      | fault             |
      | error message     |
      | missing done      |
      | interrupted dump  |
      | short stats       |
      | trailing bytes    |

  Scenario: Missing interface statistics are unavailable rather than zero traffic
    Given the current inventory and fixed Docker inspect and exec responses
    And an inventoried peer lacks complete statistics
    When the isolated Linux host observer collects interfaces
    Then that node reports unavailable counters instead of zero rates

  Scenario: A replaced container cannot silently reuse another node identity
    Given Docker uses Compose-prefixed network names with inventory labels
    And one container has the wrong Minicore node label
    When the isolated Linux host observer collects interfaces
    Then that node identity is rejected while other nodes remain visible

  Scenario: One missing container cannot hide other inventoried nodes
    Given Docker uses Compose-prefixed network names with inventory labels
    And one inventoried container is missing during discovery
    When the isolated Linux host observer collects interfaces
    Then the missing node is unavailable while healthy nodes still publish counters

  Scenario: Read endpoint mapping on BusyBox without JSON ip support
    Given Docker uses Compose-prefixed network names with inventory labels
    And the endpoint has only fixed interface metadata files
    When the isolated Linux host observer collects interfaces
    Then the endpoint maps through fixed read-only metadata without a shell
