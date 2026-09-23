"""Test-only delayed operation and short session timers. Not copied into images."""

import asyncio
import os
from pathlib import Path

from minicore_mcp.model import Topology
from minicore_mcp.policy import Policy
from minicore_mcp.server import Server


class DelayedServer(Server):
    async def handle_tools_call_async(self, request_id, params):
        if params.get("name") == "get_routes":
            await asyncio.sleep(0.8)
        return await super().handle_tools_call_async(request_id, params)


root = Path(os.environ["TEST_ROOT"])
server = DelayedServer(
    Topology(root / "inventory/topology.json", Path(os.environ["TEST_TMP"]) / "observations.json"),
    Policy("authenticated", Path(os.environ["TEST_TMP"]) / "tokens.json"),
    root / "web-ui/dist",
)
server.streamable_http_keepalive_seconds = 0.1
server.streamable_http_session_ttl_seconds = float(os.environ.get("TEST_TTL", "1800"))
asyncio.run(
    server.run_streamable_http_async(
        host="127.0.0.1",
        port=int(os.environ["TEST_PORT"]),
        endpoint="/mcp",
        max_request_bytes=2 * 1024 * 1024,
    )
)
