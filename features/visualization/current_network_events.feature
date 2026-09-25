@implemented @browser
Feature: Volatile network events panel
  Scenario: Validate bounded observer projection and expiry without topology integration
    When the isolated network events model tests are run
    Then the isolated network events model contract passes

  Scenario: Export a standalone network events panel for later parent integration
    When the isolated network events modules are loaded
    Then the standalone NetworkEvents panel export is available

  Scenario: Rates use source seconds and preserve changes across the whole current window
    Then multi-sample history retains route changes and counts each interface direction once

  Scenario: Malformed lifetime metadata cannot keep an observer row alive
    Then oversized lifetimes invalid source enums and conflicting identities are rejected

  Scenario: Incomplete observations cannot generate a withdrawal or a traffic rate
    Then truncated failed and reset-counter samples suppress unsafe comparisons

  Scenario: Open live events in a compact panel and inspect without applying faults
    Then the network events panel scopes rows highlights a node and never mutates the lab

  Scenario: Pausing the list does not extend a row lifetime
    Then an expired event disappears while paused and failed refreshes cannot restore it

  Scenario: Ignore an obsolete node response after selecting a link
    Then only the newly selected link records appear after a delayed node response

  Scenario: Link rates match each endpoint with its own previous sample
    Then interleaved endpoint samples produce both directional link rates

  Scenario: Repeated fetches cannot renew a record lifetime
    Then a repeating observer response with the same acquisition expires even while fetches succeed
