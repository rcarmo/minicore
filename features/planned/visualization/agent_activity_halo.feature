@planned @agent-activity
Feature: Highlight nodes accessed by an agent with a synthwave halo
  As a demonstrator watching the network
  I want a brief live halo around nodes being accessed through MCP
  So that I can follow agent activity without changing the topology or health display

  Scenario: Start the halo on a validated node-directed request
    Given an agent request is authorised and has a valid inventory node target
    When the management service begins handling that node operation
    Then a node activity start event is published
    And a synthwave halo appears around that node without waiting for topology polling
    And the node label, state colour and graph position remain unchanged
    And the halo means MCP request activity rather than successful node contact

  Scenario Outline: Finish the halo on every request outcome
    Given a node has one active agent request
    When the request finishes with <outcome>
    Then its activity record is closed
    And the halo briefly fades unless another request is active
    And the result does not change the halo into a network-health indicator
    Examples:
      | outcome                 |
      | successful evidence     |
      | a failed probe result   |
      | backend_not_configured  |
      | execution error         |
      | timeout                 |
      | cancellation            |

  Scenario: Keep a node highlighted while requests overlap
    Given two agent requests are active against the same node
    When one request finishes
    Then the node halo stays active
    When the remaining request finishes
    Then the halo fades once without flickering

  Scenario: Highlight each directly accessed node independently
    Given agents are accessing p1 and ce2 at the same time
    When their activity events arrive
    Then each directly accessed node has its own halo
    And no intervening nodes or links are animated as an inferred traffic path

  Scenario: A probe highlights its execution node rather than an inferred path
    Given an agent runs an approved probe from p1 towards an endpoint
    When the request starts
    Then p1 receives an activity halo
    And the destination and intermediate routers are not marked accessed unless separate node requests occur

  Scenario Outline: Exclude traffic that is not a node-directed agent operation
    When <operation> occurs
    Then it does not start a node-request activity halo
    Examples:
      | operation                              |
      | an unauthorised or invalid request      |
      | tools discovery or list_nodes          |
      | a browser node selection               |
      | a background topology or log sample    |
      | a host lifecycle command               |
      | an SSE heartbeat                       |
      | a God-only fault mutation              |

  Scenario: Keep controller activity out of the agent-visible stream
    Given a God principal is applying a fault
    And an Operator agent is reading a node
    When the Agent-view activity stream is produced
    Then the ordinary node read may produce a halo
    And the fault request produces no ordinary activity event or hidden controller metadata
    And God fault state uses its own source-labelled annotations in God view

  Scenario: Keep the activity stream minimal
    When an authorised viewer receives node activity
    Then the event contains a server request identifier, node identifier, lab generation and request lifecycle state
    And it excludes command arguments, result payloads, credentials and controller records
    And it does not assert a particular agent identity from a shared role credential

  Scenario: Reconcile after a lost finish event
    Given the viewer loses its activity stream while a halo is active
    When the activity connection reopens
    Then current active requests are reconciled from the service snapshot
    And completed requests no longer keep a halo lit
    And unknown stream state is labelled rather than reported as ongoing access indefinitely

  Scenario: Ignore duplicate or late activity events
    Given an activity completion has already been applied
    When a duplicate or older start event for the same request arrives
    Then it cannot restart the halo
    And events from a different generation or obsolete visibility request are discarded

  Scenario: Make a brief access perceptible without a history interface
    Given an authorised node request starts and finishes quickly
    When the browser renders the activity
    Then a short bounded halo cue remains perceptible
    And it automatically disappears without accumulating an activity timeline

  Scenario: Honour reduced motion and accessible selection
    Given the viewer requests reduced motion or uses the node list
    When an agent accesses a node
    Then reduced motion shows a steady activity ring without pulsation
    And the corresponding node row indicates agent access as text
    And the activity cue does not obscure the selection indicator or intercept clicks
