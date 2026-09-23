@implemented @python @access
Feature: Current service access and input boundaries
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario Outline: Discover exactly the role-specific tools
    When "<role>" requests tool discovery
    Then exactly "<tool_count>" tools are exposed for that role
    And every tool has explicit read-only and destructive annotations
    Examples:
      | role     | tool_count |
      | operator | 5          |
      | god      | 9          |

  Scenario Outline: Deny a guessed God tool before executing it
    When "operator" calls "<tool>" with arguments "{}"
    Then the RPC error is "authorization_denied"
    And the topology generation remains unchanged
    Examples:
      | tool                 |
      | list_fault_scenarios |
      | get_fault_state      |
      | apply_fault          |
      | reset_lab            |

  Scenario Outline: Reject unsafe diagnostic parameters
    When "operator" calls "<tool>" with arguments '<arguments>'
    Then the RPC error is "<error>"
    Examples:
      | tool           | arguments                                                     | error              |
      | get_routes     | {"node_id":"alien"}                                           | unknown_node       |
      | get_routes     | {"node_id":"p1","command":"id"}                               | invalid_arguments  |
      | get_routes     | {"node_id":"p1","prefix":"::/0"}                               | invalid_prefix     |
      | get_interfaces | {"node_id":"p1","interface":"../../etc/passwd"}                | unknown_interface  |
      | get_neighbors  | {"node_id":"p1","protocol":"rip"}                             | invalid_arguments  |
      | ping           | {"node_id":"p1","destination":"8.8.8.8"}                      | denied_destination |
      | ping           | {"node_id":"p1","destination":"172.30.250.11"}                | denied_destination |
      | ping           | {"node_id":"p1","destination":"10.200.1.3","count":true}      | invalid_arguments  |
      | ping           | {"node_id":"p1","destination":"10.200.1.3","count":6}         | invalid_arguments  |
      | ping           | {"node_id":"p1","destination":"$(id)"}                       | denied_destination |
      | list_nodes     | {"mode":"god"}                                                | invalid_arguments  |

  Scenario Outline: Authentication fails closed for unsupported identity
    When authentication is attempted with "<identity>"
    Then no principal is authenticated
    Examples:
      | identity           |
      | missing            |
      | bad bearer         |
      | malformed basic    |
      | god basic          |
      | forged role header |

  Scenario: Anonymous access requires the explicit private profile
    Given the explicit private profile is selected
    When an anonymous request is authenticated
    Then its only role is Operator
    And a supplied invalid credential is not downgraded to anonymous

  Scenario Outline: Reject unsafe credential configuration at startup
    When the credential configuration is "<configuration>"
    Then service policy construction fails
    Examples:
      | configuration  |
      | missing        |
      | identical keys |
      | short key      |
      | unknown role   |
      | bad profile    |

  Scenario: Browser Basic authentication grants only Operator
    When authentication is attempted with "operator basic"
    Then its only role is Operator
