@logs @initial
Feature: Stream real node container logs without container control in the viewer
  As a lab viewer
  I want recent logs for the selected node and live update notifications
  So that I can inspect actual events without losing topology context

  Scenario: Collect only declared node sources
    Given the host collector loads the canonical network inventory
    When it collects node logs
    Then it reads only timestamped stdout and stderr of declared node services
    And management logs and fault-controller audit are not collected
    And the management container retains no Docker socket or execution privilege

  Scenario: Display real startup failure evidence
    Given a declared FRR node fails during startup and emits a capability error
    When its container logs are collected and its Logs tab is opened
    Then the actual startup error is visible as container-source evidence
    And the UI does not claim that routing is healthy

  Scenario: Follow new node events
    Given the selected node has a current log page
    When its collected log revision changes
    Then the node SSE stream sends a logs.changed invalidation
    And the UI fetches the latest bounded log page
    And entries have stable IDs, timestamps, sources and severity
    And repeated snapshots do not duplicate entries
    And graph selection and camera remain unchanged

  Scenario: Pause while reading
    Given the Logs tab is following recent entries
    When I pause following
    Then the current rows and scroll position remain unchanged
    And new events are indicated without replacing the page
    When I resume following
    Then the UI fetches the latest page

  Scenario: Reconcile after stream failure
    Given the log SSE stream disconnects
    Then periodic polling continues while following
    When the stream reconnects
    Then it sends a logs.snapshot invalidation and the UI fetches current state
    And it does not claim to replay every event missed while disconnected

  Scenario: Stop watching a deselected node
    Given I am watching logs for p1
    When I select p2 or leave the Logs tab
    Then the p1 stream and outstanding fetch are closed
    And delayed p1 results never populate the p2 inspector

  Scenario: Bound history browsing
    Given the collector retains at most 500 recent entries in a bounded snapshot
    When I request older entries with a valid page cursor
    Then a bounded older page is returned without duplicates
    When the retained snapshot has rotated
    Then its old cursor returns cursor_expired
    And I can return to the latest page

  Scenario Outline: Do not equate unavailable logs with no events
    Given the log source is <condition>
    When its page is requested
    Then the response reports <error>
    And retained rows if any are marked stale rather than silently fresh

    Examples:
      | condition | error |
      | absent from the lab | node_unavailable |
      | not configured | backend_not_configured |
      | older than 15 seconds | collector_stale |
      | malformed or oversized | invalid_log_snapshot |
      | from another lab generation | generation_mismatch |
      | a command timeout | collection_timeout |

  Scenario: Distinguish a successful empty collection
    Given a running node produced no logs in the last 15 minutes
    When a successful collection is served
    Then its status is ok with an empty entry list
    And the UI says no events in this window

  Scenario Outline: Reject unsafe or excessive log requests
    When a client requests <request>
    Then the HTTP service rejects it before reading node data
    And no command is issued from the HTTP service

    Examples:
      | request |
      | an unknown node |
      | an arbitrary path |
      | an unapproved source |
      | duplicate query parameters |
      | a negative or greater than 500 limit |
      | a malformed cursor |
      | an arbitrary command or regex |

  Scenario: Redact and render untrusted messages as text
    Given a node emits credential assignments, bearer tokens, URL credentials, private key blocks, terminal escapes and HTML text
    When its logs are collected and displayed
    Then recognized secrets and private key contents are removed before persistence
    And configured lab credentials are removed
    And the API applies redaction again before returning entries
    And HTML and terminal sequences cannot execute in the browser
    And unknown severity remains unknown rather than a guessed diagnosis

  Scenario: Apply the same access policy to pages and streams
    Given the authenticated profile is selected
    When a client without credentials requests a node log page or log event stream
    Then both requests are denied
    And an Operator can read logs but cannot mutate or reset the node

  Scenario: Bound resource use and cancellation
    When collectors and browser streams are active
    Then each collection has a deadline and output cap
    And at most two node collections run at once
    And streams have bounded lifetime, writer timeout and subscriber count
    And stopping the host collector terminates child log commands
    And closing a browser stream releases its subscriber slot
