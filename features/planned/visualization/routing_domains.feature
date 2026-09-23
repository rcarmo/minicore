@planned @domains
Feature: Visualise routing domains without changing the data topology
  As a network viewer
  I want routing-domain groupings over the stable lab graph
  So that I can distinguish administrative membership from connectivity

  Scenario: Group BGP speakers by their declared autonomous systems
    Given the baseline topology contains the provider and two customer autonomous systems
    When the viewer selects the AS domain layer
    Then p1, p2, pe1 and pe2 appear in the declared AS 65000 group
    And ce1 appears in AS 65001 and ce2 appears in AS 65002
    And host1 and host2 are labelled attached endpoints without BGP speaker membership
    And the existing node positions and data links are unchanged

  Scenario: Show an OSPF area at interface scope
    Given area 0 is declared on provider interfaces and loopbacks
    When the viewer selects the OSPF area layer
    Then the five provider data links are highlighted as declared area 0 links
    And passive loopbacks have area membership without a peer edge
    And customer access, endpoint LAN and management links are not classified as OSPF links

  Scenario: Retain declared membership when collection is absent
    Given no runtime routing observations are available
    When the viewer selects a routing-domain layer
    Then declared membership is displayed with a declared-source label
    And runtime membership is unknown
    And the groups do not imply established routing sessions

  Scenario: Surface conflicting declared and observed membership
    Given the configured AS of a node differs from a fresh observed AS
    When the node is selected
    Then both values and their sources are shown
    And the mismatch is explicit
    And the graph does not silently move the node or rewrite its declared baseline

  Scenario: Switch layers without losing inspection context
    Given a node is selected and its logs or configuration are open
    When the viewer switches between AS, OSPF area and no domain grouping
    Then the selected node, camera and inspector remain available
    And the legend describes the active grouping

  Scenario: Use the same domain information without the WebGL scene
    Given the graph is unavailable or the viewer uses keyboard navigation
    When the viewer opens the node-domain matrix
    Then every visible node has the same membership and source labels as the graph
    And selecting a row opens the same node inspector
    And membership and state do not rely on colour alone
