@implemented @host
Feature: Validate isolated network event models and module exports
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

