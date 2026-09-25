import asyncio
import importlib.util
import threading
import time
from pathlib import Path
from unittest.mock import patch

from behave import then, when


@when('a "{source}" file operation is delayed during a live request')
def slow_read(c, source):
    started = threading.Event()
    done = threading.Event()
    c.early_timer = False

    def slow(original):
        def invoke(*a, **kw):
            started.set()
            time.sleep(0.18)
            try:
                return original(*a, **kw)
            finally:
                done.set()

        return invoke

    import minicore_mcp.server as server

    path = "/api/v1/topology"
    if source == "credentials":
        target = patch.object(c.policy, "reload", side_effect=slow(c.policy.reload))
    elif source == "topology":
        target = patch.object(c.topology, "snapshot", side_effect=slow(c.topology.snapshot))
    elif source == "logs":
        path = "/api/v1/nodes/p1/logs"
        target = patch.object(c.server.log_store, "page", side_effect=slow(c.server.log_store.page))
    elif source == "configuration":
        path = "/api/v1/nodes/p1/config"
        target = patch.object(server, "baseline", side_effect=slow(server.baseline))
    else:
        path = "/assets/main.js"
        original = Path.read_bytes

        def delayed(file, *a, **kw):
            return (
                slow(original)(file, *a, **kw)
                if file.name == "main.js"
                else original(file, *a, **kw)
            )

        target = patch.object(Path, "read_bytes", delayed)

    async def run():
        async def timer():
            await asyncio.sleep(0.025)
            c.early_timer = started.is_set() and not done.is_set()

        tick = asyncio.create_task(timer())
        c.slow_response = await c.server.handle_http_request_async(
            method="GET",
            path=path,
            headers={"authorization": "Bearer " + "o" * 40},
            body=b"",
            peer="127.0.0.1",
        )
        await tick

    with target:
        asyncio.run(run())
    c.read_source = source


@then("an independent timer runs before that file operation finishes")
def responsive(c):
    assert c.early_timer, "filesystem operation blocked the event loop"


@then("the requested response keeps its expected authorization and shape")
def shape(c):
    assert c.slow_response.status in ({200, 503} if c.read_source == "logs" else {200}), (
        c.slow_response.body
    )


@when("topology acquisition overlaps a generation change")
def topology_race(c):
    async def run():
        started = threading.Event()
        release = threading.Event()
        original = c.topology.snapshot

        def delayed():
            result = original()
            started.set()
            release.wait(0.3)
            return result

        async def advance():
            while not started.is_set():
                await asyncio.sleep(0.001)
            c.topology.inventory["generation"] += 1
            release.set()

        task = asyncio.create_task(advance())
        with patch.object(c.topology, "snapshot", side_effect=delayed):
            c.racy_response = await c.server.handle_http_request_async(
                method="GET",
                path="/api/v1/topology",
                headers={"authorization": "Bearer " + "o" * 40},
                body=b"",
                peer="127.0.0.1",
            )
        await task

    asyncio.run(run())


@then("the returned topology uses the current generation")
def current_generation(c):
    import json

    assert json.loads(c.racy_response.body)["generation"] == c.topology.inventory["generation"]


def pool_api():
    assert importlib.util.find_spec("minicore_mcp.file_io") is not None, (
        "bounded asynchronous file adapter unavailable"
    )
    from minicore_mcp.file_io import FileIO

    return FileIO


@when("a slow off-loop file job is cancelled while another job waits")
def cancel_worker(c):
    async def run():
        pool = pool_api()(workers=1, capacity=1)
        started = threading.Event()
        release = threading.Event()

        def work():
            started.set()
            release.wait(1)
            return 1

        first = asyncio.create_task(pool.run(work))
        while not started.is_set():
            await asyncio.sleep(0.001)
        first.cancel()
        await asyncio.sleep(0.02)
        c.worker_drained = not first.done()
        try:
            await pool.run(lambda: 2)
        except OSError as exc:
            c.busy_code = str(exc)
        finally:
            release.set()
        result = await asyncio.gather(first, return_exceptions=True)
        c.was_cancelled = isinstance(result[0], asyncio.CancelledError)
        c.after_worker = await pool.run(lambda: 3)
        await pool.close()

    asyncio.run(run())


@then("cancellation does not free a live worker slot early")
def drain_held(c):
    assert (
        c.worker_drained
        and c.busy_code == "file_io_busy"
        and c.was_cancelled
        and c.after_worker == 3
    )


@when("all admitted file jobs are waiting on a blocked worker")
def bounded_admission(c):
    async def run():
        pool = pool_api()(workers=1, capacity=2)
        release = threading.Event()
        started = threading.Event()

        def work():
            started.set()
            release.wait(1)

        a = asyncio.create_task(pool.run(work))
        b = asyncio.create_task(pool.run(work))
        while not started.is_set():
            await asyncio.sleep(0.001)
        await asyncio.sleep(0.01)
        try:
            await pool.run(lambda: None)
        except OSError as exc:
            c.admission_code = str(exc)
        finally:
            release.set()
        await asyncio.gather(a, b)
        await pool.close()

    asyncio.run(run())


@then("an extra request fails with file_io_busy without growing the queue")
def busy_admission(c):
    assert c.admission_code == "file_io_busy"


@when("an independent wire client requests a deliberately slow log file")
def wire_slow_file(c):
    from mcp_harness.wire import Wire

    wire = c.async_wire = Wire()
    c.add_cleanup(wire.close)
    result = wire.request("GET", "/fixture/slow-file")
    assert result[0] == 200, result
    c.slow_wire_future = wire.pool.submit(wire.request, "GET", "/api/v1/nodes/p1/logs")
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if wire.request("GET", "/fixture/slow-file-status")[2]["started"]:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("slow file never started")
    started = time.monotonic()
    c.wire_ping = wire.rpc("ping")
    c.wire_health = wire.request("GET", "/healthz")
    c.wire_elapsed = time.monotonic() - started
    c.file_still_pending = not c.slow_wire_future.done()
    c.slow_wire_result = c.slow_wire_future.result(timeout=3)


@then("MCP ping and HTTP health complete before the log response")
def wire_responsive(c):
    assert c.wire_ping[0] == 200 and c.wire_ping[2]["result"] == {} and c.wire_health[0] == 200
    assert c.file_still_pending and c.wire_elapsed < 0.5 and c.slow_wire_result[0] == 503, (
        c.wire_elapsed,
        c.file_still_pending,
    )


@when("an SSH key metadata check is deliberately delayed")
def slow_key(c):
    from minicore_mcp.ssh_adapter import SSHAdapter

    key = c.root / "ssh"
    key.mkdir()
    (key / "diagnostic").write_text("test")
    (key / "known_hosts").write_text("test")
    adapter = SSHAdapter(c.topology, key)
    c.ssh_timer = False
    entered = threading.Event()
    done = threading.Event()
    exists = Path.exists

    def slow(path):
        if path.name == "diagnostic":
            entered.set()
            time.sleep(0.15)
            done.set()
        return exists(path)

    async def run():
        async def timer():
            await asyncio.sleep(0.02)
            c.ssh_timer = entered.is_set() and not done.is_set()

        tick = asyncio.create_task(timer())

        async def fail(*_, **kwargs):
            raise OSError()

        with (
            patch.object(Path, "exists", slow),
            patch("asyncio.create_subprocess_exec", side_effect=fail),
        ):
            try:
                c.ssh_result = await adapter.execute("p1", {"operation": "get_routes"})
            except OSError:
                c.ssh_result = {"error_code": "node_unavailable"}
        await tick

    asyncio.run(run())


@then("adapter failure is bounded while loop timers continue")
def ssh_check_free(c):
    assert c.ssh_timer and c.ssh_result["error_code"]


@when("an owned host journal write is deliberately delayed")
def host_journal_delay(c):
    import importlib.util

    module_spec = importlib.util.spec_from_file_location(
        "async_host", Path(__file__).resolve().parents[2] / "scripts/host-fault-controller.py"
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    module.JOURNAL = c.root / "host-state.json"
    original = module.save_ownership
    entered = threading.Event()
    done = threading.Event()
    running = True

    def save(value):
        entered.set()
        time.sleep(0.15)
        original(value)
        done.set()

    async def command(argv):
        nonlocal running
        if argv[1] == "inspect":
            return 0, b"true" if running else b"false", b""
        running = argv[1] == "start"
        return 0, b"", b""

    async def run():
        async def timer():
            await asyncio.sleep(0.02)
            c.host_free = entered.is_set() and not done.is_set()
            c.host_locked = module.lock.locked()

        tick = asyncio.create_task(timer())
        with (
            patch.object(module, "run", side_effect=command),
            patch.object(module, "save_ownership", side_effect=save),
        ):
            async with module.lock:
                result = await module.execute({"scenario": "zap-node-p1", "action": "apply"})
            assert result["ok"]
        await tick
        if hasattr(module, "files"):
            await module.files.close()

    asyncio.run(run())


@then("host loop timers continue and mutation remains serialized")
def host_free(c):
    assert c.host_free and c.host_locked


@when("the web file-reader budget is exhausted")
def exhausted_http(c):
    from unittest.mock import AsyncMock

    async def run():
        with patch.object(
            c.server.files, "run", new_callable=AsyncMock, side_effect=OSError("file_io_busy")
        ):
            c.exhausted_response = await c.server.handle_http_request_async(
                method="GET",
                path="/api/v1/nodes/p1/logs",
                headers={"authorization": "Bearer " + "o" * 40},
                body=b"",
                peer="127.0.0.1",
            )

    asyncio.run(run())


@then("the response is 503 file_io_busy rather than an internal server error")
def busy_http(c):
    import json

    assert (
        c.exhausted_response.status == 503
        and json.loads(c.exhausted_response.body)["error_code"] == "file_io_busy"
    )


@when("a topology stream reads a deliberately slow observation file")
def slow_stream_read(c):
    entered = threading.Event()
    done = threading.Event()
    original = c.topology.snapshot

    def read():
        entered.set()
        time.sleep(0.15)
        result = original()
        done.set()
        return result

    async def run():
        response = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/events",
            headers={"authorization": "Bearer " + "o" * 40},
            body=b"",
            peer="127.0.0.1",
        )
        with patch.object(c.topology, "snapshot", side_effect=read):
            task = asyncio.create_task(anext(response.stream))
            await asyncio.sleep(0.03)
            activity = await c.server.handle_http_request_async(
                method="GET",
                path="/api/v1/activity",
                headers={"authorization": "Bearer " + "o" * 40},
                body=b"",
                peer="127.0.0.1",
            )
            c.stream_free = activity.status == 200 and entered.is_set() and not done.is_set()
            await task
        await response.stream.aclose()

    asyncio.run(run())


@then("a concurrent activity snapshot remains responsive")
def stream_free(c):
    assert c.stream_free
