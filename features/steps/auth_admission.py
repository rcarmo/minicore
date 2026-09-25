import asyncio
import json
import threading
import time
from unittest.mock import AsyncMock, patch

from behave import then, when
from minicore_mcp.policy import Policy


@when("34 HTTP callers arrive while credential reload is blocked")
def auth_queue(c):
    async def run():
        entered = threading.Event()
        release = threading.Event()
        original = Policy.reload

        def slow(policy):
            entered.set()
            release.wait(2)
            return original(policy)

        async def request():
            return await c.server.handle_http_request_async(
                method="GET",
                path="/api/v1/activity",
                headers={"authorization": "Bearer " + "o" * 40},
                body=b"",
                peer="127.0.0.1",
            )

        with patch.object(Policy, "reload", slow):
            first = asyncio.create_task(request())
            while not entered.is_set():
                await asyncio.sleep(0.001)
            rest = [asyncio.create_task(request()) for _ in range(33)]
            await asyncio.sleep(0.03)
            c.auth_busy_responses = [t.result() for t in rest if t.done()]
            waiting = next(t for t in rest if not t.done())
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)
            replacement = asyncio.create_task(request())
            await asyncio.sleep(0.01)
            c.auth_replacement_waits = not replacement.done()
            release.set()
            c.auth_results = await asyncio.gather(first, *rest, replacement, return_exceptions=True)
        c.auth_after = await request()

    asyncio.run(run())


@then("two callers receive 503 file_io_busy without waiting for reload")
def auth_busy(c):
    assert len(c.auth_busy_responses) == 2, len(c.auth_busy_responses)
    for response in c.auth_busy_responses:
        assert response.status == 503
        assert json.loads(response.body) == {"error_code": "file_io_busy"}


@then("cancelling a waiting caller releases its authentication admission")
def auth_cancelled(c):
    assert c.auth_replacement_waits and c.auth_after.status == 200
    assert sum(isinstance(r, asyncio.CancelledError) for r in c.auth_results) == 1


@then("every remaining admitted caller authenticates after reload completes")
def auth_recovered(c):
    assert sum(getattr(r, "status", 0) == 200 for r in c.auth_results) == 32
    assert c.policy._auth_pending == 0


@when('an independent "{transport}" client reaches a full authentication queue')
def wire_auth_busy(c, transport):
    from mcp_harness.wire import Wire

    wire = c.auth_wire = Wire()
    c.add_cleanup(wire.close)
    assert wire.request("GET", "/fixture/auth-fill")[0] == 200
    start = time.monotonic()
    c.wire_busy_response = (
        wire.request("GET", "/api/v1/topology")
        if transport == "HTTP"
        else wire.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}})
    )
    c.wire_busy_duration = time.monotonic() - start


@then("it receives a temporary 503 file_io_busy response")
def wire_busy_response(c):
    status, _, payload = c.wire_busy_response
    assert status == 503 and payload == {"error_code": "file_io_busy"}, c.wire_busy_response
    assert c.wire_busy_duration < 0.5


@then("a health request remains responsive and authentication recovers")
def wire_auth_recovery(c):
    assert c.auth_wire.request("GET", "/healthz")[0] == 200
    assert c.auth_wire.request("GET", "/fixture/auth-release")[0] == 200
    assert c.auth_wire.request("GET", "/api/v1/topology")[0] == 200
    assert c.auth_wire.initialize()[0]
    assert (
        c.auth_wire.request(
            "GET", "/api/v1/topology", role=None, extra={"Authorization": "Bearer invalid"}
        )[0]
        == 401
    )


@when("an activity stream reauthenticates against exhausted file capacity")
def auth_stream_busy(c):
    async def run():
        response = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/activity/events",
            headers={"authorization": "Bearer " + "o" * 40},
            body=b"",
            peer="127.0.0.1",
        )
        with patch.object(
            c.server.auth_files, "run", new_callable=AsyncMock, side_effect=OSError("file_io_busy")
        ):
            try:
                c.busy_auth_event = await anext(response.stream)
            except StopAsyncIteration:
                c.busy_auth_event = None
            finally:
                await response.stream.aclose()
        c.busy_auth_streams = c.server.streams

    asyncio.run(run())


@then("the stream closes without yielding an event or leaking a slot")
def auth_stream_closed(c):
    assert c.busy_auth_event is None and c.busy_auth_streams == 0


@when('"{method}" dispatch encounters exhausted authentication file capacity')
def dispatch_auth_busy(c, method):
    from umcp_shared import MCPRequestContext

    async def run():
        with patch.object(
            c.server.auth_files, "run", new_callable=AsyncMock, side_effect=OSError("file_io_busy")
        ):
            c.auth_dispatch = await c.server.process_request_async(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 19,
                        "method": method,
                        "params": {"name": "list_nodes", "arguments": {}},
                    }
                ),
                context=MCPRequestContext(
                    transport="streamable-http", headers={"authorization": "Bearer " + "o" * 40}
                ),
            )

    asyncio.run(run())


@then("dispatch returns file_io_busy without an internal or credential error")
def dispatch_busy_code(c):
    assert c.auth_dispatch["error"]["message"] == "file_io_busy", c.auth_dispatch
    assert c.auth_dispatch["error"]["code"] == -32000
