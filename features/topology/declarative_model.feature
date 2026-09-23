@initial @model
Feature: One representation drives containers and the network view
  Scenario: Render the complete topology before starting routers
    Given the eight-node topology from the brief is loaded
    And no runtime observations have been collected
    When a customer requests the topology
    Then the graph contains p1, p2, pe1, pe2, ce1, ce2, host1 and host2
    And it contains the five provider links, two customer links and two endpoint links
    And every node and link is expected but its routing state is unknown
    And shared management membership does not create data links

  Scenario: Generate reproducible Compose and routing configuration
    Given the canonical topology contains stable node, interface and network identities
    When the deployment files are generated twice
    Then both generations produce identical Compose and FRR configurations
    And each node maps to exactly one Compose service
    And each data link maps to a separate internal bridge with two declared endpoints
    And the Docker gateway address is reserved independently of the endpoint addresses
    And endpoint defaults point to the customer router rather than the Docker gateway

  Scenario Outline: Reject ambiguous or unsafe topology
    Given the topology contains <invalid_condition>
    When the model is validated
    Then generation fails before a container command is issued

    Examples:
      | invalid_condition |
      | duplicate node or service IDs |
      | a link to an unknown node |
      | an interface reused by two links on the same node |
      | overlapping IP subnets |
      | an endpoint using the Docker gateway address |
      | an invalid interface name |

  Scenario: Observe container presence without inventing routing health
    Given a host-side collector observes that p1 is running and p2 is stopped
    When the management service reads the matching generation observations
    Then p1 has container state running and unknown routing state
    And p2 has container state exited and unavailable node state
    And all unobserved links remain unknown

  Scenario Outline: Discard unusable observations
    Given an observation file is <condition>
    When the topology is requested
    Then expected nodes and links remain visible
    And runtime collection is unavailable
    And no previously healthy routing state is invented

    Examples:
      | condition |
      | malformed |
      | older than 45 seconds |
      | for another lab |
      | for another generation |
