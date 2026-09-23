@implemented @python @mcp-security
Feature: Isolate MCP execution and cancellation between callers
  Scenario: Check every role against every advertised tool
    When authenticated Operator and God clients exercise all nine known tools
    Then discovery and direct calls enforce the same capability matrix
    And unavailable execution has native tool errors without credentials in responses

  Scenario: Keep client-supplied role and session fields from escalating privilege
    When an Operator forges role information in headers, query and tool arguments
    Then no request receives God-only results or changes generation

  Scenario: Session ownership applies to all session HTTP methods
    When an Operator presents a God session on POST, GET and DELETE
    Then each request is denied and the God session remains usable

  Scenario: Cancel only a request owned by the same authenticated session
    Given two MCP sessions are executing requests with the same request ID
    When the first session cancels its request
    Then only its own request is cancelled and the other completes successfully

  Scenario: Cancel only a request owned by the same principal
    Given Operator and God are executing requests with the same request ID
    When Operator cancels its request
    Then the God request is unaffected

  Scenario: A progress token is not a cancellation target
    Given a request has a progress token different from its request ID
    When cancellation names only that progress token
    Then the request continues until its own request ID is cancelled

  Scenario: Reject concurrent duplicate request IDs within one scope
    Given a scoped request is already executing
    When the same session starts another request with the same ID
    Then the duplicate is rejected without replacing or cancelling the first request

  Scenario: Cancelling from a different session cannot affect an active call
    Given a request is executing in one Operator session
    When another Operator session sends cancellation for that ID
    Then the first request remains active

  Scenario: Deny stateless cancellation across unrelated HTTP connections
    Given an authenticated stateless request is executing
    When a separate stateless HTTP connection sends cancellation for its ID
    Then the cancellation is denied and the active request is unaffected

  Scenario: Reject wrong-typed identities without an authorization-hook exception
    When a client sends a non-string tool name or method
    Then it receives a validation or authorization failure without HTTP 500
