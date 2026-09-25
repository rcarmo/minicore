# Compose services

`compose.json` is generated from `inventory/topology.json`. Run `make generate`; do not edit the generated file. `make up` starts management on host loopback port 19000. Its ingress bridge permits Docker port publication while internal management and data bridges remain separate.

`make router-build lab-up` builds the plain-IP FRR image and starts all eight lab nodes. Each router mounts its own generated `frr.conf` and `daemons` files and has per-daemon health checks. `make watch-logs` starts the host log and presence collector without mounting the Docker socket into management.

Use `make bdd-boot` for live boot, peer, packet and log checks. See the [runbook](../docs/operations/runbook.md) for credentials and optional host services, and [limitations](../docs/operations/known-limitations.md) before changing the default exposure.
