# Restricted node evidence tools

The five Operator diagnostic tools return inventory, interface state, FRR routes, BGP or OSPF neighbours, and bounded ICMP evidence when `MINICORE_SSH_DIR` is configured. The browser Interfaces and Routing tabs use the same bounded adapters. Fault execution remains separate. Fixtures without SSH return `backend_not_configured`.

## Identity and execution

- `make ssh-provision` creates separate diagnostic and fault client identities plus one pinned Ed25519 host key per router.
- Management mounts `secrets/http`, `secrets/ssh/client` and `secrets/ssh/fault-client` read-only. Diagnostic requests use only the diagnostic identity in `secrets/ssh/client`. The separate fault identity is mounted for controller traffic and is independently restricted by each router `fault_authorized_keys` entry to `/usr/local/bin/minicore-fault`.
- Diagnostic UID 11001 differs from the workspace file-owner UID. Root-owned forced-command and key policy, plus read-only FRR mounts, prevent configuration or authorisation edits.
- SSH listens only on each router's declared management address. Node SSH ports are not host-published. Key authentication only; no PTY, agent, X11, TCP forwarding, uncontrolled environment or root login.
- The fixed remote command is `minicore-dispatch`. JSON stdin is validated again on the node: known operation, exact field list, canonical IPv4 prefixes, inventoried interfaces and destinations, and probe bounds. Execution uses fixed executable argument arrays only.
- Node execution has its own deadline and output cap. Management uses pinned `known_hosts`, `StrictHostKeyChecking=yes`, `BatchMode`, `IdentitiesOnly`, one attempt, 5-second connect timeout and 15-second total budget. Cancellation kills and reaps the local SSH process group. Node execution has a separate 12-second watchdog.
- Routers add `SYS_CHROOT` for OpenSSH privilege separation. They do not add `SYS_ADMIN` or privileged mode. Management gains an SSH client and a named non-root user only.

## Response contract

`get_routes(node_id, prefix?)` returns bounded router JSON, bounded raw evidence, correlation fields, lab and generation, collection time and duration. A missing exact prefix is a successful empty result. Malformed output is `parse_failure`. Host-key mismatch, SSH authentication failure, connection timeout, node unavailability, execution timeout and output limit remain distinct error codes.

`GET /api/v1/nodes/{id}/routes?prefix=...` uses the same validation and adapter as the MCP tool. The browser Routing tab displays that response and raw evidence. Sequential reads can have different uptime or age fields; compare route content and next hops, not incidental timer values.

## Reproduce

```sh
make generate
make ssh-provision
make router-build
make build
make lab-up
make up
make live-routes
make acceptance
make mcp-client
```

Provisioning is repeatable without replacing existing keys. The separate fault identity exists for privilege separation. The browser never receives private keys or arbitrary SSH access.
