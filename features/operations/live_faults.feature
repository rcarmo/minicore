@external @fault-recovery
Feature: Inject and reset each real lab fault through God MCP
  Scenario: Run all three scenarios twice through separate role clients
    Given the isolated local lab and separate God and Operator credentials
    When the official SDK applies each fixed scenario twice with a reset between runs
    Then fault state is verified and Operator evidence exposes the corresponding measured changes
    And every reset restores peerings and bidirectional traffic before advancing generation
    And Operator cannot discover or invoke controller tools or receive controller ground truth
    And no fault mutation appears in the ordinary agent activity stream
    And a failure cleanup resets the lab rather than leaving a test fault active
