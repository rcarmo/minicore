@implemented @python @mcp-protocol
Feature: Verify MCP transport with independent clients and hostile wire inputs
  Scenario Outline: Negotiate a supported protocol and preserve session state
    When an independent wire client negotiates "<version>"
    Then initialized, discovery, schema annotations, tool results and session deletion obey that protocol
    Examples:
      | version    |
      | 2025-03-26 |
      | 2024-11-05 |

  Scenario: Reject unsupported follow-up versions without corrupting a session
    When an MCP session receives a missing or unsupported protocol version
    Then the response declares the supported versions and the valid session still works

  Scenario: Validate protocol fallback during initialization
    When a client proposes a protocol newer than the server supports
    Then initialization selects a supported version rather than claiming the proposed version

  Scenario: Process protocol ping without calling a network node
    When an authenticated client sends MCP ping
    Then the JSON-RPC result is an empty object and no node operation runs

  Scenario Outline: Reject malformed JSON-RPC requests with stable errors
    When a wire client sends malformed RPC case "<case>"
    Then the response is a bounded client error rather than a server error or dropped connection
    Examples:
      | case                 |
      | invalid JSON         |
      | batch array          |
      | boolean request ID   |
      | invalid version      |
      | parameters array     |
      | tool name array      |
      | tool arguments array |
      | unknown tool         |

  Scenario Outline: Reject ambiguous framing and unsuitable content
    When a wire client sends HTTP case "<case>"
    Then the transport rejects the request without executing a tool
    Examples:
      | case                    |
      | duplicate authorization |
      | duplicate content length|
      | transfer encoding       |
      | oversized body          |
      | wrong content type      |
      | unsupported accept      |
      | foreign origin          |

  Scenario: Expire and recreate an in-memory session
    When an inactive session reaches its configured expiry
    Then reuse returns unknown session and a fresh initialization succeeds

  Scenario: Invalidate sessions on server restart
    When the test service restarts with the same credentials
    Then the old session is rejected and reinitialization restores discovery

  Scenario: Reconnect MCP event streaming without replay guarantees
    When a session event stream is opened, disconnected and reconnected
    Then its framing is valid, duplicate attachment is refused, and deletion closes the stream

  Scenario: Rotate credentials through a service restart
    When the Operator credential is replaced and the service restarts
    Then old credentials fail on POST, GET and DELETE while the new credential initializes successfully

  Scenario: Accept combined list-valued Accept headers without weakening singleton validation
    When the client sends repeated Accept fields listing JSON and event streams
    Then the request succeeds while duplicated credentials remain invalid
