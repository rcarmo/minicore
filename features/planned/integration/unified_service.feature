@planned

Feature: Expose Minicore through one application service
  As a lab consumer
  I want one service endpoint for the UI, topology updates, and MCP
  So that the first deployment has a small and understandable footprint

  Scenario: Serve the topology application
    Given the Python application service is ready
    When a customer requests the application entry point
    Then the service returns the production Preact application assets
    And those assets were built and tested using Bun

  Scenario: Expose factual topology updates
    Given the Python application service is ready
    When a customer requests a topology snapshot
    Then the service returns the versioned combined topology model
    When the customer opens the topology event stream
    Then the same service emits factual topology invalidations

  Scenario: Expose MCP separately within the same process
    Given the Python application service is ready
    When an approved external agent connects to the MCP endpoint
    Then the service negotiates Streamable HTTP at the configured MCP path
    And MCP tools remain governed by their diagnostic allow-list
    And Operator UI routes do not expose God controls

  Scenario: Isolate transport failures
    Given the topology snapshot API remains available
    When the SSE stream is temporarily unavailable
    Then periodic polling can still reconcile the UI
    And the service does not report the observed network as failed because a transport failed

  Scenario: Run without front-end development tooling
    Given a production container image has been built
    Then it contains the generated web assets
    And the Python service serves those assets directly
    And Bun is not required by the running service unless explicitly justified
