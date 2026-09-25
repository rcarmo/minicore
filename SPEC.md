# Minicore specification

Build an IP network simulator for demonstrating troubleshooting techniques. Use synthetic addresses, real FRRouting daemons and Linux forwarding under Docker Compose.

## Requirements

- Six routers, two packet endpoints and nine data links from one declarative inventory.
- OSPF and BGP with measured interface, route, peer and packet evidence.
- A restricted MCP endpoint with bounded operations and inventory-only targets.
- Reversible faults and verified baseline recovery.
- Separate management and data paths; no Docker socket or elevated host capabilities in management.
- A 3D topology workbench with diagnostic panels.
- Gherkin-first changes, executable acceptance and reproducible operating instructions.

Requirements describe the intended contract. Inspect the code and executable tests in each revision to determine implemented behaviour.
