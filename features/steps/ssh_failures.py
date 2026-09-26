import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when
from minicore_mcp.ssh_adapter import SSHAdapter


def execute(c, mode):
    (c.fixture / "mode").write_text(mode)
    with patch.dict(
        os.environ,
        {"PATH": str(c.fixture) + ":" + os.environ["PATH"], "SSH_FIXTURE_ROOT": str(c.fixture)},
    ):
        return asyncio.run(c.adapter.execute("p1", {"operation": "get_routes"}))


@given("a pinned-key adapter and a recording SSH process fixture")
def adapter_fixture(c):
    c.fixture = c.root / "ssh-fixture"
    c.fixture.mkdir()
    shutil.copy("tests/ssh_process_fixture.py", c.fixture / "ssh")
    (c.fixture / "ssh").chmod(0o755)
    for name in ["diagnostic", "known_hosts"]:
        (c.fixture / name).write_text("test-only")
    c.adapter = SSHAdapter(c.topology, c.fixture)


@when('the SSH fixture returns "{failure}"')
def failure(c, failure):
    modes = {
        "changed host key": "host",
        "bad credentials": "auth",
        "connection timeout": "connect",
        "unavailable node": "absent",
        "malformed JSON": "malformed",
        "wrong data shape": "shape",
        "false error status": "false_error",
        "unexpected fields": "fields",
        "output cap": "cap",
        "deadline": "hang",
    }
    if failure == "deadline":
        original = asyncio.timeout
        with patch(
            "minicore_mcp.ssh_adapter.asyncio.timeout", side_effect=lambda _: original(0.15)
        ):
            c.result = execute(c, modes[failure])
    else:
        c.result = execute(c, modes[failure])


@then('the adapter error is "{error}" with no successful evidence')
def stable_error(c, error):
    assert c.result["error_code"] == error, c.result
    assert (
        c.result["status"] == "unavailable"
        and c.result["data"] is None
        and c.result["raw_evidence"] == ""
    ), c.result


@when("the SSH fixture exceeds the combined output budget")
def combined(c):
    c.result = execute(c, "combined")


@when("a node operation is cancelled while SSH and a child process are running")
def cancelled(c):
    (c.fixture / "mode").write_text("hang")

    async def run():
        task = asyncio.create_task(c.adapter.execute("p1", {"operation": "get_routes"}))
        for _ in range(100):
            if (c.fixture / "pids").exists():
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("SSH fixture never started")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            c.cancelled = True
        else:
            c.cancelled = False

    with patch.dict(
        os.environ,
        {"PATH": str(c.fixture) + ":" + os.environ["PATH"], "SSH_FIXTURE_ROOT": str(c.fixture)},
    ):
        asyncio.run(run())


@then("the operation propagates cancellation")
def propagates(c):
    assert c.cancelled


@then("the fixture process group no longer has live processes")
def reaped(c):
    pids = [int(p) for p in (c.fixture / "pids").read_text().split()]

    def live(pid):
        try:
            return Path(f"/proc/{pid}/stat").read_text().split()[2] not in {"Z", "X"}
        except FileNotFoundError:
            return False

    for _ in range(50):
        if not any(live(p) for p in pids):
            return
        time.sleep(0.02)
    # Cleanup is precise fixture PID cleanup, not a broad process scan.
    for pid in pids:
        if live(pid):
            os.kill(pid, 9)
    raise AssertionError("SSH fixture process leak")


@then("adapter concurrency slots are released")
def released(c):
    assert c.adapter.global_slots._value == 8 and c.adapter.node_slots["p1"]._value == 2


@when("an SSH parent exits while a child holds the output pipe open")
def orphan(c):
    original = asyncio.timeout
    # Include interpreter startup under CPU contention, then require recorded PIDs.
    # 150 ms could expire before this fixture spawned any descendants.
    with patch("minicore_mcp.ssh_adapter.asyncio.timeout", side_effect=lambda _: original(2)):
        c.result = execute(c, "orphan")


@then("the operation reaches its deadline")
def deadline(c):
    assert c.result["error_code"] == "execution_timeout"


@when("multiple node requests execute concurrently through the adapter")
def concurrency(c):
    (c.fixture / "mode").write_text("concurrency")

    async def run():
        return await asyncio.gather(
            *(
                c.adapter.execute(node, {"operation": "get_routes", "prefix": f"192.0.2.{i}/32"})
                for i, node in enumerate(["p1", "p1", "p1", "p2", "pe1", "pe2", "ce1", "ce2"] * 3)
            )
        )

    with patch.dict(
        os.environ,
        {"PATH": str(c.fixture) + ":" + os.environ["PATH"], "SSH_FIXTURE_ROOT": str(c.fixture)},
    ):
        c.results = asyncio.run(run())


@then("no node executes more than two SSH processes and the global maximum is eight")
def bounded_concurrency(c):
    events = sorted(
        [json.loads(line) for line in (c.fixture / "events").read_text().splitlines()],
        key=lambda e: e["at"],
    )
    active = {}
    for event in events:
        if event["event"] == "start":
            active[event["pid"]] = event["node"]
        else:
            active.pop(event["pid"])
        assert len(active) <= 8
        assert all(list(active.values()).count(n) <= 2 for n in active.values())
    assert not active


@then("every result belongs to its own completed request")
def own_result(c):
    assert len(c.results) == 24 and all(r["status"] == "ok" for r in c.results)
    assert len({r["data"]["request"]["prefix"] for r in c.results}) == 24


@when("the adapter succeeds and then the same node becomes unavailable")
def no_cache(c):
    assert execute(c, "ok")["status"] == "ok"
    c.result = execute(c, "absent")


@then("the second result contains no cached success or raw evidence")
def no_stale(c):
    stable_error(c, "node_unavailable")


@when("the adapter invokes the recording SSH fixture")
def invoke(c):
    c.result = execute(c, "ok")


@then("it uses a fixed dispatcher, pinned known hosts, batch key-only login and no forwarding")
def argv(c):
    c.argv = json.loads((c.fixture / "events").read_text().splitlines()[0])["argv"]
    for value in [
        "StrictHostKeyChecking=yes",
        "BatchMode=yes",
        "IdentitiesOnly=yes",
        "ClearAllForwardings=yes",
        "RequestTTY=no",
        "ConnectionAttempts=1",
    ]:
        assert value in c.argv
    assert "UserKnownHostsFile=" + str(c.fixture / "known_hosts") in c.argv


@then("no caller parameter becomes an SSH executable, identity or target")
def argv_safe(c):
    assert c.argv[-2:] == ["diagnostic@172.30.250.11", "minicore-dispatch"]
