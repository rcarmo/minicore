@implemented @browser
Feature: Volatile network events panel
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

  Scenario: Conflicting record identities are rejected before rendering
    Then two rows with the same source acquisition cannot hide behind different display timestamps

  Scenario: Show which link endpoint is unavailable
    Then a partial link response names the failed endpoint with a plain status message

  Scenario: A failed endpoint does not erase the healthy endpoint's rate
    Then a partial link keeps matching healthy source rates and labels the failed source
