# God fault toolbar

God-authenticated browser sessions can switch to God view and use fixed targeted fault controls.

## Use

Authenticate as God, enable *God mode*, then choose one toolbar mode:

- *Inspect* selects nodes and links without mutation.
- *⚡ Zap* stops a selected node container, or disables both ends of a selected physical link. The management service is not a selectable target.
- *⚄ Corrupt* applies one compatible fixed corruption selected from the inventory-derived catalogue for the chosen router or link: 100 ms delay, 25% loss or a fixed endpoint-LAN prefix blackhole on a router. The chosen scenario is persisted before execution and retried unchanged for the same request body.
- *Restore lab* reverses the active fault, verifies baseline routing and traffic, then advances generation.

The armed mode is visible, exclusive and per tab. Escape disarms. One target click executes the action and returns to Inspect. While a request runs, other actions are disabled. Failed or lost responses offer retry with the same request body. View and generation changes clear pending UI state.

## Host control boundary

Management does not mount the Docker socket or receive host capabilities. An opt-in host user service accepts a bounded Unix-socket message from UID 10001 and compiles only inventory-derived scenario and action pairs into fixed `docker`, `ip` and `tc` argument arrays. It does not accept caller-supplied container names, commands, addresses or extra fields. There is no host TCP listener.

`runtime/host-control` is group 10001 with setgid, and its socket is mode `0660`. The host service runs as the existing host user with Docker permission, not as a new root daemon. Its private journal is outside the management mount at `runtime/host-fault-journal`, with directory mode `0700` and file mode `0600`.

Before mutation, the host verifies a clean target and fsyncs ownership. Reset changes only owned scenarios. Ownership survives restart and clears only after measured recovery. Foreign qdiscs and routes are rejected. `tc` parameter parsing handles nested seconds and fraction JSON. The blackhole route uses protocol 198 and metric 1 so it wins over the baseline BGP route. Router-root and host-root remain trusted operators of this synthetic lab.

Host commands have a 12-second deadline and 64 KiB combined output limit, read all pipe chunks and clean their process groups. Management transport has a 20-second deadline. A singleton host lock and the controller lock serialise mutations. Reset in management verifies the full baseline after the host reports target restoration.

## Browser and API policy

Only God may POST `/api/v1/faults/apply` or `/api/v1/faults/reset`. Requests need the configured exact browser `Origin`, JSON content type, `X-Minicore-Intent: fault-control`, a bounded body and strict arguments. Origin and header checks address browser CSRF. Credentials still provide authentication.

The controller remains the public source of fault state, generation and audit. The chosen corruption result is persisted before execution and replayed for a matching idempotency key. Reusing a key with different arguments conflicts. If a completed result has expired but its intent remains, retry returns `idempotency_expired` and does not execute again. Loaded intent maps are bounded and validated. Private intent maps are excluded from state projection.

The MCP tool count is unchanged: six Operator tools and ten God-visible tools. Targeted selection is a browser API only. Existing God `get_fault_state` and `reset_lab` also inspect and recover targeted effects. The host backend must stay enabled while a targeted fault is active.

## Start and stop

```sh
make host-fault-start
MINICORE_HOST_FAULT_SOCKET=/run/host-control/fault.sock make up
```

Targeted host control is opt-in. `MINICORE_HOST_FAULT_SOCKET` defaults to empty. Keep the override on later `make up` calls while targeted faults are in use. `MINICORE_BROWSER_ORIGIN` defaults to `http://127.0.0.1:19000`.

Restore a verified baseline before disabling host control:

```sh
# Restore through the God UI or existing God reset_lab tool first.
make up
make host-fault-stop
```

Both the host fault service and log service are user-systemd services and are not auto-enabled at boot. On failure, inspect the private ownership journal and service journal. Do not delete an owned-fault journal to force a clean state. Restart the service and run explicit *Restore lab*.
