@implemented @browser
Feature: Cross-browser accessible evidence workbench
  Scenario: Inspect nodes and routing with or without a graphics context
    Then accessible node controls and routing comparisons work without relying on WebGL

  Scenario: Clear privileged content independently in two browser tabs
    Then God annotations never appear in an Agent tab and revocation clears the privileged tab

  Scenario: Reject obsolete prefix requests on every browser engine
    Then a late first-prefix response cannot replace the second prefix evidence

  Scenario: Keep header controls grouped and reachable on tablets
    Then the header replaces generation with God mode and keeps all controls inline with accessible touch targets
