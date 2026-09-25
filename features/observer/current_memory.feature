@implemented @python @routing-observer
Feature: Retain only bounded recent observer records in memory
  Scenario: Expire records and delta baselines at exactly sixty seconds
    Given an observer with a controllable monotonic clock
    When routing and counter records reach sixty seconds old
    Then neither current records nor previous comparison baselines remain

  Scenario: Receipt of delayed IPC does not renew acquisition age
    Given an observer with a controllable monotonic clock
    When a host record arrives sixty seconds after its acquisition
    Then it is discarded rather than becoming a fresh sample

  Scenario: Hard memory and record bounds evict oldest complete records
    Given a small bounded observer store
    When more complete records arrive than its capacity
    Then memory and entry limits hold and eviction is reported

  Scenario: Stop restart or scope identity change cannot replay prior observations
    Given an observer with a controllable monotonic clock
    When its lab generation or source incarnation changes
    Then no prior identity record or comparison baseline is returned

  Scenario: Responses have an independent byte limit and never refresh retention
    Given an observer with a controllable monotonic clock
    When a scoped response cannot fit all eligible records
    Then whole records are truncated with omitted counts within the response limit
    And a second read does not change the acquisition times

  Scenario: Reject caller data outside the observer schema
    Given an observer with a controllable monotonic clock
    When arbitrary payload bytes or raw output are submitted to the store
    Then they are rejected and no observer data reaches the filesystem

  Scenario: Share single-flight sources across concurrent readers
    Given a coordinator with two bounded asynchronous sources
    When concurrent clients read while collection is pending
    Then each source executes at most once and cancelling a reader does not stop collection

  Scenario: A stalled source cannot block a healthy source or loop timers
    Given a coordinator with two bounded asynchronous sources
    When one source stalls beyond its deadline
    Then the healthy source is published and the loop remains responsive
    And coordinator shutdown clears observations and releases all tasks

  Scenario: Parsed IGMP fields fit the volatile schema without raw packet retention
    Given an observer with a controllable monotonic clock
    When valid v2 and v3 reports are parsed and put into the observer
    Then both typed events are present without packet bytes or application fields

  Scenario: An in-flight old generation cannot repopulate a reset observer
    Given a coordinator with two bounded asynchronous sources
    When the store generation changes during a slow successful collection
    Then the old collection result is discarded before publication

  Scenario: A retained host sample from before reset cannot enter the new generation
    Given an observer with a controllable monotonic clock
    When a reset is followed by an old but unexpired host sample
    Then the new generation remains empty until a newly acquired sample arrives

  Scenario: Source recovery cannot compare across a failed observation
    Given an observer with a controllable monotonic clock
    When successful route samples are separated by a failed read
    Then recovery starts a new comparison baseline

  Scenario: Multicast group cardinality is bounded independently of record count
    Given an observer with a controllable monotonic clock
    When reports introduce more than 256 distinct multicast groups
    Then only 256 groups remain and overflow is reported

  Scenario: A silent collector cannot keep source health live indefinitely
    Given an observer with a controllable monotonic clock
    When an interface source stops updating for more than three seconds
    Then its retained rows stay timestamped but source health is delayed

  Scenario: Loss counters belong only to the affected observation scope
    Given an observer with a controllable monotonic clock
    When IGMP capture drops one record on p1
    Then p1 IGMP reports the loss reason and p2 interface counters report no missed updates

  Scenario: Repeated errors cannot extend the age of earlier loss counts
    Given an observer with a controllable monotonic clock
    When three IGMP drops are followed by one new drop fifty seconds later
    Then after sixty seconds only the new drop remains in the source window
