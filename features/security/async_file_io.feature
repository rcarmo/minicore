@implemented @python @async-files
Feature: Keep MCP and web responsive while filesystem operations are slow
  Background:
    Given an isolated management service with Operator and God credentials

  Scenario Outline: Slow file reads do not stop event loop timers
    When a "<source>" file operation is delayed during a live request
    Then an independent timer runs before that file operation finishes
    And the requested response keeps its expected authorization and shape
    Examples:
      | source        |
      | credentials   |
      | topology      |
      | logs          |
      | configuration |
      | asset         |

  Scenario: A topology read cannot publish a previous generation after reset
    When topology acquisition overlaps a generation change
    Then the returned topology uses the current generation

  Scenario: Bounded file workers retain their slots until cancelled I/O drains
    When a slow off-loop file job is cancelled while another job waits
    Then cancellation does not free a live worker slot early

  Scenario: File worker admission has a hard upper bound
    When all admitted file jobs are waiting on a blocked worker
    Then an extra request fails with file_io_busy without growing the queue

  Scenario: A slow file read leaves independent wire MCP and HTTP requests responsive
    When an independent wire client requests a deliberately slow log file
    Then MCP ping and HTTP health complete before the log response

  Scenario: SSH credential metadata checks cannot block the async adapter
    When an SSH key metadata check is deliberately delayed
    Then adapter failure is bounded while loop timers continue

  Scenario: Host fault ownership fsync cannot block its event loop
    When an owned host journal write is deliberately delayed
    Then host loop timers continue and mutation remains serialized

  Scenario: Saturated file readers return a typed HTTP error
    When the web file-reader budget is exhausted
    Then the response is 503 file_io_busy rather than an internal server error

  Scenario: Topology and log SSE generators do not block on file reads
    When a topology stream reads a deliberately slow observation file
    Then a concurrent activity snapshot remains responsive
