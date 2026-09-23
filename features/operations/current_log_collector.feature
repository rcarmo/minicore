@implemented @host
Feature: Collect bounded container evidence without service-side Docker access
  Background:
    Given a temporary copy of the host tools and canonical inventory

  Scenario: Redact node output before persistence
    Then the collector removes recognized credentials and private keys but retains ordinary event text

  Scenario: Assign stable event identity and bound retained evidence
    Then repeated messages have stable distinct IDs within a container incarnation and snapshots fit the size cap

  Scenario: Terminate bounded command execution
    Then the collector kills over-limit and timed-out children

  Scenario: Bound individual messages and the collection time window
    Then long log messages are truncated and old or malformed lines are excluded

  Scenario: Collect declared nodes only with fixed log requests
    Given a recording Docker executable instead of a real daemon
    When the log collector runs once
    Then only inventoried node services are requested with timestamp, tail and time-window bounds
    And atomic log snapshots contain no management records or raw credentials
    And the collector removes its lock on exit

  Scenario: Reject an unknown selected node before collection
    Given a recording Docker executable instead of a real daemon
    When the log collector requests an unknown node
    Then it fails without calling Docker

  Scenario: Refuse overlapping host collectors
    Given a collector lock already exists
    When the log collector runs once
    Then it fails without removing another collector's lock
