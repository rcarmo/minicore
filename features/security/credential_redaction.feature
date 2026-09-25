@implemented @python @credential-redaction
Feature: Keep configured credentials out of evidence during rotation
  Background:
    Given an isolated management service with Operator and God credentials
    And evidence contains the current token as ordinary text

  Scenario Outline: Revoked credentials remain redacted from retained evidence
    When the Operator credential rotates and evidence is read through "<surface>"
    Then only the new credential authenticates
    And the evidence succeeds without exposing the retired token
    Examples:
      | surface            |
      | HTTP logs          |
      | HTTP configuration |
      | MCP logs           |
      | MCP configuration  |

  Scenario Outline: Rotation during evidence collection cannot expose a newly configured token
    When "<source>" collection overlaps credential rotation
    Then the in-flight evidence is withheld with redaction_unavailable
    And a fresh request redacts both old and new credentials
    Examples:
      | source        |
      | logs          |
      | configuration |

  Scenario Outline: Redaction memory has a fixed fail-closed budget
    When credential rotation exceeds the redaction "<budget>" budget
    Then the credential change still revokes the old identity
    And log and configuration evidence fail closed on HTTP and MCP
    And topology remains available with the new identity
    Examples:
      | budget |
      | count  |
      | bytes  |

  Scenario: Invalid reload does not erase retired-secret redaction
    When credential reload fails before a valid replacement is installed
    Then both current and replaced tokens stay redacted

  Scenario: Exhausted redaction publishes only unavailable log metadata on SSE
    When credential rotation exceeds the redaction "count" budget
    And a log event stream is opened with the new credential
    Then the stream reports unavailable redaction without evidence text
