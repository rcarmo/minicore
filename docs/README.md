# Documentation

[Minicore](../README.md) provides an IP network simulator, diagnostic APIs and reversible fault exercises. [SPEC.md](../SPEC.md) defines the overall requirements.

```text
docs/
├── specs/          Detailed runtime, API and browser contracts
├── operations/     Setup, recovery, limitations and dependencies
├── development/    Engineering methodology and executable coverage
└── images/         README illustration
```

## Operate the simulator

- [Runbook](operations/runbook.md)
- [Known limitations](operations/known-limitations.md)
- [Dependencies and licences](operations/dependencies.md)

## Diagnostics and control

- [MCP roles and authorisation](specs/mcp-capability-modes.md)
- [Restricted node adapter](specs/live-node-adapter.md)
- [Fault controller and recovery](specs/fault-controller.md)
- [God toolbar](specs/god-fault-toolbar.md)
- [Container logs](specs/log-streaming.md)
- [Declared configuration](specs/configuration-browser.md)
- [Routing and IGMP observer](specs/routing-observer.md)

## Workbench

- [Topology visualisation](specs/visualization.md)
- [Visual design](specs/visual-direction.md)
- [Routing layers and comparison](specs/routing-visualization.md)
- [Node evidence browser](specs/node-evidence-browser.md)
- [Agent and God views](specs/visibility-and-activity.md)
- [Agent activity](specs/agent-activity.md)
- [Network events](specs/network-events-panel.md)

## Develop and test

- [Engineering and testing methodology](development/methodology.md)
- [Implementation patterns](development/engineering-references.md)
- [Generated behaviour coverage](development/behavior-coverage.md)
- [Contributor instructions](../AGENTS.md)
