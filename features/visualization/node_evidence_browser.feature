Feature: Browse bounded evidence for a selected network node
  As a customer viewing the Minicore topology
  I want to inspect a node's factual state and logs
  So that I can understand the available evidence without leaving the graph

  Background:
    Given the combined topology contains an inventory-known node
    And the customer is permitted to view that node's evidence

  Scenario: Open the inspector from the graph
    When the customer selects the node
    Then the graph keeps the node visibly selected
    And a docked inspector identifies the node and its role
    And the inspector shows the collection time and freshness
    And the graph camera and filters are preserved

  Scenario: Browse node logs
    Given the selected node has allow-listed FRR events in the requested time window
    When the customer opens the Logs tab
    Then the UI requests a bounded page for that node
    And entries are ordered deterministically
    And each entry shows its time, source, severity, and plain-text message
    And the response identifies truncation and pagination state

  Scenario: Continue through bounded history
    Given the current log page has a next cursor
    When the customer requests the next page
    Then the service returns the next bounded page
    And the UI does not duplicate entries already displayed

  Scenario: Notify the reader of new evidence
    Given the customer is reading older entries
    When SSE announces newer evidence for the selected node
    Then the UI indicates that new events are available
    And it preserves the reader's scroll position
    And it does not grow the browser log buffer without a bound

  Scenario: Node evidence is temporarily unavailable
    Given the selected node remains part of the expected topology
    When evidence collection times out
    Then the graph remains visible
    And the inspector reports evidence as unavailable with a stable error code
    And the UI does not represent the node as healthy or failed solely because collection failed

  Scenario: Lab reset separates evidence generations
    Given the inspector displays evidence from lab generation 7
    When an operator reset creates lab generation 8
    Then evidence from generation 7 is marked as historical
    And it is not silently merged with generation 8 evidence

  Scenario Outline: Reject unsafe log requests
    When a client requests logs using <unsafe_input>
    Then the service rejects the request with a stable denied or validation error
    And no arbitrary command or path is executed

    Examples:
      | unsafe_input |
      | an unknown node ID |
      | an arbitrary filesystem path |
      | an unapproved log source |
      | an unbounded time range |
      | a limit above the server maximum |
      | shell syntax in a filter |

  Scenario: Show measured evidence in the inspector
    When the inspector displays a routing event
    Then it identifies the observed source and message
    And it labels only measured network state
    And it does not expose operator fault ground truth
