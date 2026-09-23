@implemented @python @ssh-failures
Feature: Bound SSH execution and reject misleading node results
  Background:
    Given a pinned-key adapter and a recording SSH process fixture

  Scenario Outline: Classify SSH and node failures without stale success
    When the SSH fixture returns "<failure>"
    Then the adapter error is "<error>" with no successful evidence
    Examples:
      | failure             | error                     |
      | changed host key    | host_key_mismatch         |
      | bad credentials    | ssh_authentication_failed |
      | connection timeout | connection_timeout        |
      | unavailable node   | node_unavailable          |
      | malformed JSON     | parse_failure             |
      | wrong data shape   | parse_failure             |
      | false error status | parse_failure             |
      | unexpected fields  | parse_failure             |
      | output cap         | output_limit              |
      | deadline           | execution_timeout         |

  Scenario: Bound combined standard output and error rather than each stream separately
    When the SSH fixture exceeds the combined output budget
    Then the adapter error is "output_limit" with no successful evidence

  Scenario: Cancel and reap the local SSH process tree
    When a node operation is cancelled while SSH and a child process are running
    Then the operation propagates cancellation
    And the fixture process group no longer has live processes
    And adapter concurrency slots are released

  Scenario: Reap descendants even after the SSH parent exits
    When an SSH parent exits while a child holds the output pipe open
    Then the operation reaches its deadline
    And the fixture process group no longer has live processes

  Scenario: Enforce per-node and global concurrency without returning cached results
    When multiple node requests execute concurrently through the adapter
    Then no node executes more than two SSH processes and the global maximum is eight
    And every result belongs to its own completed request

  Scenario: A failed collection cannot reuse an earlier successful result
    When the adapter succeeds and then the same node becomes unavailable
    Then the second result contains no cached success or raw evidence

  Scenario: Pin connection policy and reject arbitrary identity input
    When the adapter invokes the recording SSH fixture
    Then it uses a fixed dispatcher, pinned known hosts, batch key-only login and no forwarding
    And no caller parameter becomes an SSH executable, identity or target
