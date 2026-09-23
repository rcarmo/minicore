@planned

@compose
Feature: Manage known lab containers from the host
  Scenario: Start management without starting routers
    Given generated Compose configuration is current
    When the owner starts the default Compose service
    Then only the management service starts
    And its public mapping is loopback-only by default
    And its health check reports management readiness rather than network health

  Scenario: Start the declared network separately
    Given address overlap and local runtime prerequisites have been checked
    When the owner starts the lab profile
    Then Compose starts six FRR routers and two endpoints
    And endpoints are not attached to the management network
    And routers do not publish SSH or routing daemon ports

  Scenario Outline: Resolve host lifecycle operations through inventory
    Given the owner invokes the host lifecycle command for p1
    When the requested action is <action>
    Then the command resolves p1 to its declared Compose service
    And it issues fixed arguments without shell interpolation
    And no unrelated project container is targeted

    Examples:
      | action |
      | start |
      | stop |
      | restart |
      | status |

  Scenario: Reject an arbitrary container name
    When the owner names a container absent from the topology
    Then the lifecycle helper fails validation
    And Docker is not called

  Scenario: Publish safe container observations atomically
    When the owner collects container status
    Then the observation file includes lab ID, generation, collection time and logical node states
    And readers never observe a partially written file
    And container IDs, credentials and operator control history are excluded

  Scenario: Keep host control out of management
    When the management image and Compose service are inspected
    Then the service runs as a non-root user with no Linux capabilities
    And it has no Docker socket, host network or host process namespace
    And runtime observations are mounted read-only
    And the host lifecycle script is not included in the runtime image
