# Minicore runbook

Use this runbook to install, operate and recover the simulator. [SPEC.md](../../SPEC.md) defines its contracts; [dependencies](dependencies.md) lists pinned components.

## Install and start

Requirements: Linux amd64; Docker 28+ with isolated bridge mode; Compose 2.36+; Bun 1.4.1; Python 3.12+; Make; user-systemd. Keep at least 3 GiB free for source builds and test dependencies.

```sh
make bootstrap generate          # full Python lock and frozen Bun lock
make acceptance
make router-build build
bun scripts/init-secrets.ts      # once; refuses overwrite, prints no values
sudo chown 10001:$(id -g) secrets/http/mcp-tokens.json
sudo chmod 640 secrets/http/mcp-tokens.json
make ssh-provision               # pinned host keys, separate forced identities
make lab-up up watch-logs
```

Provisioning needs sudo for UID/GID 10001 files. Management is read-only, non-root, and has no Docker socket. The router build removes four SYS_ADMIN capability declarations from checksum-pinned FRR source. Do not replace this with privileged mode or a blanket capability grant.

UI: `http://127.0.0.1:19000`; MCP: `/mcp`. A full lab runs nine services. `make status` reports container state. `make live-routes` and verified God reset check routing. `make observe` refreshes host presence once.

## Authentication

The default `private` profile allows anonymous Operator access on loopback. God uses a separate configured God credential. To require credentials for all access:

```sh
MINICORE_EXPOSURE_PROFILE=authenticated make up
```

Credential reload admits at most 32 concurrent callers, including those waiting for the reload lock. Excess HTTP and MCP transport requests return `503 file_io_busy`; retry after a delay. Invalid credentials still return 401. Existing evidence streams close if reauthentication cannot obtain capacity; reconnect to obtain a fresh snapshot.

MCP uses Bearer. Browser Basic accepts username `operator` or `god` with the matching token. No token is stored in frontend application state. Rotate the token by replacing the token file atomically with the same service-read permissions. Malformed or removed configured files fail closed. Existing evidence streams reauthenticate before their next event. Existing bounded operations can complete; mutation callers reconcile by idempotency key.

The service keeps configured token values in a process-local redaction set after rotation. Its limit is 128 values or 64 KiB. At that limit, log and configuration reads return `redaction_unavailable`, but credential changes still take effect. To recover, remove retired tokens from declared configuration and container log sources, replace retained log snapshots with sanitised data, then restart management. Do not restart merely to clear the limit while source evidence still contains old tokens: the previous redaction set is not restored after restart.

Do not publish the private profile. Remote use needs TLS, authentication and source filtering.

## God toolbar and restore

```sh
make host-fault-start
MINICORE_HOST_FAULT_SOCKET=/run/host-control/fault.sock make up
```

The host service is `minicore-faults.service`. Its socket mount is opt-in through the environment override above. Keep the override on later `make up` calls while targeted faults are active. In God view, arm Zap or Corrupt, then click one node or link. Zap stops the whole node container or disables both link ends. Corrupt chooses one compatible fixed effect; retries keep the same choice. Escape returns to Inspect. Restore lab checks baseline peerings and sourced packets before it advances generation.

The legacy four God MCP operations still work. `get_fault_state` and `reset_lab` also inspect and recover targeted faults. Never delete `runtime/control` or `runtime/host-fault-journal` to clear an active or uncertain fault. Restart the host service, query state, then reset explicitly. A disk error, foreign route or qdisc, or failed verification stays an error.

After verified baseline, disable the host socket with `make up` using the default empty setting, then run `make host-fault-stop`. Do not disable it with a stopped node waiting for recovery. See [God fault toolbar](../specs/god-fault-toolbar.md) for ownership, request and audit semantics.

## Inspection

- The main graph is 3D. Layer controls open compact 2D diagnostic graphs and tables in floating panels. Panels drag by title, move by arrow keys, scroll internally, and minimise.
- Summary, Interfaces, and Routing refresh every five seconds while selected. Routing panels pause when minimised. Each source keeps its own failure and timestamp. Failed collection does not create a down link or a withdrawn route.
- Logs use SSE updates with polling fallback. Pause, Follow latest, Older, and severity filters are available. Retention is 15 minutes, 500 rows, and 60 KiB per snapshot. A stale collector is labelled.
- Configuration shows generated saved files, not collected running configuration. There is no write path.
- God view adds fault state. Operator view excludes it server-side. Agent halos are authorised MCP reads, not browser collection or fault mutations.

## Collector and lifecycle

`minicore-logs.service` starts with `make watch-logs`; stop it with `make stop-logs`. Neither host service is enabled at machine boot. Check them with `systemctl --user status minicore-logs.service minicore-faults.service` and inspect the user journal for failures.

An abrupt process stop can leave the empty `runtime/log-collector.lock` directory. First confirm that no `log-collector.ts` or `log-watcher.ts run` process is alive. Only then run `rmdir runtime/log-collector.lock` and restart `make watch-logs`. Never remove a live lock. Logs go stale after 15 seconds; presence after 45 seconds.

For network driver upgrades, restore baseline, stop collection, run `make down` without the volume flag, rebuild, then run `make lab-up up watch-logs` with the intended host-controller override. This keeps host credential, journal and configuration files. Avoid concurrent mutation tests.

## Verification

```sh
make acceptance
make mcp-client live-routes live-faults live-recovery live-isolation
make live-targeted live-ui-faults  # host executor enabled
make bdd-boot bdd-logs browser-matrix live-performance
make watch-logs                  # lifecycle tests deliberately stop it
```

`live-isolation` needs host sudo, tcpdump, and nsenter. It temporarily cuts both PE1 uplinks and inserts test routes. Cleanup restores them. If the harness is killed, restore `pe1` interfaces `to-p1` and `to-p2`, remove the fixed test routes, and run God reset and baseline verification before you continue.

Tool surfaces: six Operator MCP tools and ten God MCP tools. Protocol versions: `2025-03-26` and `2024-11-05`. Initialize, send initialized, and keep session and version headers. Generic SSE curl is not the client-acceptance test; `make mcp-client` uses the official SDK.

## Supply chain and shutdown

Use [dependencies](dependencies.md), `locks/`, `requirements-dev.lock` and `web-ui/bun.lock`. Exact versions still depend on upstream artifact availability. Preserve the FRR source, patch and licence obligations when you redistribute.

To shut down, restore baseline, then run `make stop-logs host-fault-stop down`. Journals, keys, and generated config stay on the host.

## Network events observer

The observer stores network fields in memory for at most 60 seconds. It has no packet files, export, or application inspection. Open *Network events* for scoped Routing, Interfaces, and IGMP views. Pause affects autoscroll only; expiry continues. See the [observer contract](../specs/routing-observer.md) for limits and source semantics.

```sh
make observer-start                       # counters only, user service
MINICORE_OBSERVER_SOCKET=/run/observer/counters.sock MINICORE_HOST_FAULT_SOCKET=/run/host-control/fault.sock make up
make observer-capture-start               # switches to filtered IGMP system service
make live-observer                        # synthetic IGMP + expiry/restart tests
```

IGMP capture needs explicit sudo provisioning of `minicore-observer-capture.service`. It runs as the host account with CAP_NET_RAW only. It stops the counter-only service first. To switch back, stop capture with `make observer-capture-stop` and then run `make observer-start`. Do not launch another helper against the same socket. Neither service is enabled at boot. Keep the observer socket environment setting when you recreate management. To disable the observer, stop the selected helper and recreate management without `MINICORE_OBSERVER_SOCKET`.

Both management and capture have core dumps and swap disabled. The only observer runtime artifact is `runtime/observer-socket/counters.sock`. A restart clears the window and changes source identity. These controls do not change existing container-log retention or fault audit. Observer networking, subprocesses, collection and API/SSE paths use asyncio. See [known limitations](known-limitations.md) for filesystem worker and cancellation constraints.
