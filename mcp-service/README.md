# Management service

Python and vendored uMCP serve browser assets, topology, bounded SSE and MCP through one HTTP listener. The service uses the Python standard library; it has no external runtime Python packages.

Operator tools read inventory and measured evidence through restricted SSH. God tools call a separate fixed-scenario controller. The browser shares evidence readers and has independently authorised God controls. Unconfigured backends return `backend_not_configured`.

Container logs arrive through host-collected snapshots mounted read-only. Configuration browsing exposes declared files only. Observer data stays in memory for at most 60 seconds. Live filesystem operations use bounded off-loop workers; subprocesses, sockets and streaming use asyncio.

The container runs non-root with a read-only root filesystem, dropped Linux capabilities and no Docker socket. See the [specification](../SPEC.md), [MCP roles](../docs/specs/mcp-capability-modes.md), [runbook](../docs/operations/runbook.md) and [limitations](../docs/operations/known-limitations.md).
