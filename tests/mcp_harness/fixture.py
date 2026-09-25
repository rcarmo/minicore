"""Test-only delayed operation and short session timers. Not copied into images."""

import asyncio
import os
import threading
import time
from pathlib import Path

from minicore_mcp.model import Topology
from minicore_mcp.policy import Policy
from minicore_mcp.server import Server
from umcp_shared import MCPHTTPResponse


class DelayedServer(Server):
    # Test-only metrics and fixed event bursts; never shipped in runtime images.
    burst_slots = 0
    slow_started = threading.Event()
    slow_installed = False

    async def handle_http_request_async(self, **request):
        path = request["path"]
        if path == "/fixture/slow-file":
            if not self.slow_installed:
                original = self.log_store.page

                def slow(*args, **kwargs):
                    self.slow_started.set()
                    time.sleep(0.8)
                    return original(*args, **kwargs)

                self.log_store.page = slow
                self.slow_installed = True
            return self.response(200, {"armed": True})
        if path == "/fixture/slow-file-status":
            return self.response(200, {"started": self.slow_started.is_set()})
        if path == "/fixture/status":
            return self.response(
                200,
                {
                    "aux": self.streams,
                    "burst": self.burst_slots,
                    "mcp": sum(
                        s.writer is not None for s in self._streamable_http_sessions.values()
                    ),
                    "activity": len(
                        self.activity.snapshot(self.topology.inventory["generation"])["active"]
                    ),
                },
            )
        if path == "/fixture/burst":

            async def chunks():
                self.burst_slots += 1
                try:
                    for _ in range(256):
                        yield b"data: " + b"x" * 65520 + b"\n\n"
                finally:
                    self.burst_slots -= 1

            return MCPHTTPResponse(200, content_type="text/event-stream", stream=chunks())
        if path == "/fixture/fill-mcp":
            for session in self._streamable_http_sessions.values():
                if session.writer is not None:
                    for _ in range(100):
                        try:
                            session.queue.put_nowait(b"data: " + b"x" * 65520 + b"\n\n")
                        except asyncio.QueueFull:
                            break
            return self.response(200, {"queued": True})
        return await super().handle_http_request_async(**request)

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
