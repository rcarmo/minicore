@planned @visibility
Feature: Switch between agent-visible evidence and full lab visibility
  As an authorised demonstrator
  I want a God mode checkbox on the existing workbench
  So that I can compare the Operator agent's available evidence with lab ground truth

  Scenario: Default to the agent-visible projection
    When any viewer opens or reloads the workbench
    Then the God mode checkbox is unchecked
    And the visible projection is labelled Agent view
    And the server returns only evidence allowed by the Operator evidence contract
    And the checkbox state does not change the caller's credentials or MCP role

  Scenario: Reveal ground truth for an authorised demonstrator
    Given the viewer is authenticated with God capability
    And the God mode checkbox is unchecked
    When the viewer checks God mode
    Then the server authorises the full-visibility request
    And the workbench is labelled God view
    And declared topology, collected evidence and controller annotations have distinct source labels
    And fault target, scenario, requested impairment and verified controller outcome are visible when available
    And the graph positions, camera and still-visible selection are preserved

  Scenario: Operator credentials cannot reveal God data
    Given the viewer has only Operator or anonymous private-lab access
    When the workbench is opened
    Then the God mode checkbox is disabled with an authorisation explanation
    And a manually crafted full-visibility API or SSE request is denied server-side
    And no controller data is prefetched into the browser

  Scenario: Use existing authenticated capability without a client-side role switch
    Given the viewer is authenticated with God capability
    When the viewer toggles visibility repeatedly
    Then visibility requests are authorised against that existing capability
    And no role field supplied by the browser grants or changes capability
    And no long-lived God credential is placed in JavaScript, URLs or browser application storage

  Scenario Outline: Apply the Operator evidence boundary to every surface
    Given the God mode checkbox is unchecked
    When the viewer inspects <surface>
    Then the returned records and fields follow the same Operator evidence policy as the agent-facing contract
    And unsupported evidence is labelled unavailable rather than supplied from an admin-only source
    And controller ground truth is absent from the response
    Examples:
      | surface                         |
      | topology and node details       |
      | routing domains and peerings    |
      | prefix announcement visibility |
      | node logs                       |
      | declared configuration files   |
      | cached responses                |
      | SSE notifications               |

  Scenario: Agent view is a permission projection rather than an agent's memory
    Given the Operator contract permits an observation
    And a particular agent has not yet requested it
    When Agent view displays the observation
    Then it is labelled available to Operator agents
    And the viewer does not claim that the agent has already seen or reasoned about it
    And evidence unavailable to the Operator contract stays unavailable

  Scenario: Return safely from God view to Agent view
    Given a God-authorised viewer has ground truth visible in the graph and inspector
    When God mode is unchecked
    Then God annotations and privileged inspector content are removed immediately
    And privileged streams and requests are cancelled
    And the server is queried for a fresh Operator projection
    And privileged comparison samples and cached controller records are discarded
    And selections that exist only in God view are cleared
    And shared topology positions and the camera remain unchanged

  Scenario: Ignore an obsolete privileged response after switching off
    Given a God-view request or event is in flight
    When the viewer switches to Agent view
    And the old privileged response arrives
    Then its view identifier does not match the current request context
    And it cannot repopulate graph, inspector, table or comparison state

  Scenario: Keep visibility independent between browser views
    Given one authenticated browser tab is in God view
    And another is in Agent view
    When either tab refreshes or receives SSE events
    Then each response uses that tab's requested authorised projection
    And no process-global visibility flag changes the other tab or an agent's MCP results

  Scenario: Fail closed when privileged access is lost
    Given the browser previously displayed God view
    When a refresh or stream connection is rejected for authorisation
    Then privileged content is cleared and its stream is closed
    And the checkbox is unchecked with an access-loss message
    And Agent view is loaded only if ordinary access is still authorised

  Scenario: Full visibility does not fabricate ground truth
    Given the viewer is authorised for God view
    And no fault controller or running-configuration collector is available
    When God mode is checked
    Then those sources are labelled unavailable
    And Minicore does not report no active faults or a healthy baseline from missing controller state
    And declared configuration remains distinct from live running configuration

  Scenario: Toggling visibility never changes the lab
    Given a lab fault is active
    When the authorised viewer checks and unchecks God mode
    Then no fault is applied or reset
    And no node command, configuration write or additional probe is triggered by the checkbox
    And credentials, arbitrary commands and host secrets remain excluded even from God view

  Scenario: Change generation without mixing privileged history
    Given observations and controller records from one lab generation are displayed
    When a new generation is observed
    Then prior activity and comparison state are cleared
    And the selected authorised visibility is refetched for the new generation
    And old ground truth cannot be associated with the new baseline
