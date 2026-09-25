# MCP capability modes

Minicore exposes exactly two MCP capability profiles.

| Mode | Purpose | Capabilities |
|---|---|---|
| `operator` | Observe and probe the synthetic lab | `get_evidence`, `list_nodes`, `get_interfaces`, `get_routes`, `get_neighbors`, `ping` |
| `god` | Run controlled fault demonstrations | All Operator tools plus `list_fault_scenarios`, `apply_fault`, `get_fault_state`, `reset_lab` |

`operator` and `god` are stable code and audit role names. `God mode` is the browser label.

## Authorisation model

- The server derives capability from authenticated identity. Clients cannot select a role in tool arguments, headers, query strings or session metadata.
- One principal has one effective role for one request. `god` includes operator capabilities.
- `tools/list` is filtered. An Operator principal does not discover God-only tools.
- Each `tools/call` is authorised again. Discovery filtering is not the security boundary.
- MCP session IDs are not identity and cannot raise privilege.
- Streamable HTTP authentication and authorisation apply consistently to POST, GET and DELETE.
- Missing, invalid or ambiguous credentials fail closed.
- The local private profile can map anonymous access to `operator` only. God always requires authenticated identity.
- Credentials and principal-to-role mapping come from deployment configuration or a trusted ingress, not inventory, images, browser assets, URLs or logs.
- The browser header checkbox switches between Agent view and God view only for an already God-authorised browser session. It does not create capability.

## Fault surface

Version 1 keeps three fixed MCP scenario families only:

1. `core-link-failure`
2. `customer-bgp-failure`
3. `data-path-degradation`

`list_fault_scenarios` returns stable scenario IDs and typed bounded parameters. `apply_fault` accepts a scenario ID, validated inventory references where that scenario permits them, and an idempotency key. It does not accept commands. Only one fault may be active. Another active fault returns `fault_conflict`. Reusing a key with changed arguments returns `idempotency_conflict`.

`get_fault_state` returns bounded controller state to God only. The God browser view may display the same bounded state when the checkbox is enabled. Agent view excludes it.

`reset_lab` removes the active fault, restores the baseline, verifies baseline health and advances generation only after successful restoration. Already-baseline reset is idempotent.

## Execution boundary and audit

God capability does not grant arbitrary container privilege to the MCP process. The service calls a dedicated controller with fixed scenario protocol, independent validation, serialised mutation, deadlines, cleanup and bounded audit. Management still has no unrestricted Docker control.

Every God discovery and mutation call records UTC time, authenticated subject, effective role, request and idempotency IDs, tool name, validated scenario parameters, lab and generation before and after, authorisation decision, outcome, duration, rollback or reset verification and stable error code. Credentials are never logged.

## Browser-targeted fault surface

The God browser toolbar does not add MCP tools. It maps one click to a fixed inventory-derived catalogue of `zap-*` and `corrupt-*` scenarios, persists the selected corruption before execution, and replays the same selected scenario on retry. It does not create arbitrary, caller-defined or rerolled faults.

## Non-goals

- No third role, approval workflow, impersonation or temporary elevation.
- No arbitrary command execution in either role.
- No multiple simultaneous faults or general fault editor.
- No scheduled faults, production-target faults or caller-defined fault generation.
