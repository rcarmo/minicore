@external @live-ssh
Feature: Collect real router routes through restricted SSH and MCP
  Scenario: Return exact-prefix FRR evidence through an external MCP client
    Given diagnostic keys and pinned node host keys have been provisioned
    And the lab routers and management service are running with the SSH adapter
    When the independent MCP client calls get_routes on p1 for 10.200.8.0/29
    Then the result contains the real FRR route and next hop with bounded raw evidence
    And the structured result and text fallback agree
    And an exact missing prefix returns an empty successful result
    And the same permitted route evidence appears in the Routing inspector

  Scenario: Reject a changed host key instead of trusting the node
    Given diagnostic keys and pinned node host keys have been provisioned
    When a diagnostic request uses an incorrect pinned key for p1
    Then it returns host_key_mismatch without collecting node evidence

  Scenario: Restrict the diagnostic SSH identity independently of MCP
    Given diagnostic keys and pinned node host keys have been provisioned
    When a client requests arbitrary shell execution or configuration through the diagnostic key
    Then only the validating dispatcher runs and the request is rejected
    And forwarding and PTY requests are refused
    And the diagnostic identity cannot write the FRR configuration

  Scenario: Execute all five Operator tools against real nodes
    Given diagnostic keys and pinned node host keys have been provisioned
    And the lab routers and management service are running with the SSH adapter
    When the official MCP client invokes inventory, interfaces, routes, BGP, OSPF and ping
    Then every call returns observed evidence with matching text and structured data
    And interfaces expose only data interfaces rather than management state
    And an adjacent-router probe returns sent, received, loss and RTT measurements
    And a customer-endpoint probe without a return route reports measured loss rather than a transport failure
    And an unapproved management destination is denied before SSH execution

  Scenario: Preserve enabled empty and disabled protocol states
    Given diagnostic keys and pinned node host keys have been provisioned
    And the lab routers and management service are running with the SSH adapter
    When the official client reads provider adjacencies and a customer's undeclared OSPF
    Then the provider evidence contains Full neighbors and Established BGP peers
    And the customer OSPF request reports protocol_not_enabled
