import asyncio
import json
import subprocess
import time
from datetime import timedelta
from pathlib import Path

import httpx
from behave import given, then, when
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[2]


@given("diagnostic keys and pinned node host keys have been provisioned")
def provisioned(c):
    assert (ROOT / "secrets/ssh/client/known_hosts").exists()


@given("the lab routers and management service are running with the SSH adapter")
def running_adapter(c):
    r = httpx.get("http://127.0.0.1:19000/healthz")
    assert r.status_code == 200
    # Daemon health precedes BGP convergence; wait for the baseline route, not a fixed sleep.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        route = httpx.get(
            "http://127.0.0.1:19000/api/v1/nodes/p1/routes?prefix=10.200.8.0/29", timeout=20
        )
        if route.status_code == 200 and "10.200.8.0/29" in (route.json().get("data") or {}):
            return
        time.sleep(1)
    raise AssertionError("Baseline route failed to converge")


@when("the independent MCP client calls get_routes on p1 for 10.200.8.0/29")
def real_route(c):
    async def call():
        async with streamable_http_client("http://127.0.0.1:19000/mcp") as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=20)
            ) as client:
                await client.initialize()
                result = await client.call_tool(
                    "get_routes", {"node_id": "p1", "prefix": "10.200.8.0/29"}
                )
                absent = await client.call_tool(
                    "get_routes", {"node_id": "p1", "prefix": "192.0.2.0/24"}
                )
                return result, absent

    c.route, c.absent = asyncio.run(call())


@then("the result contains the real FRR route and next hop with bounded raw evidence")
def actual_route(c):
    assert c.route.isError is False, c.route
    r = c.route.structuredContent
    assert r["status"] == "ok" and "10.200.8.0/29" in r["data"]
    assert r["data"]["10.200.8.0/29"][0]["nexthops"]
    assert "10.200.8.0/29" in r["raw_evidence"] and len(r["raw_evidence"].encode()) <= 65536


@then("the structured result and text fallback agree")
def same(c):
    assert c.route.structuredContent == json.loads(c.route.content[0].text)


@then("an exact missing prefix returns an empty successful result")
def absent(c):
    assert not c.absent.isError and c.absent.structuredContent["data"] == {}, c.absent


@then("the same permitted route evidence appears in the Routing inspector")
def route_api(c):
    r = httpx.get("http://127.0.0.1:19000/api/v1/nodes/p1/routes?prefix=10.200.8.0/29", timeout=20)
    assert r.status_code == 200, r.text
    assert "10.200.8.0/29" in r.json()["data"]
    assert (
        r.json()["data"]["10.200.8.0/29"][0]["nexthops"]
        == c.route.structuredContent["data"]["10.200.8.0/29"][0]["nexthops"]
    )


@when("a diagnostic request uses an incorrect pinned key for p1")
def bad_host(c):
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        known = (ROOT / "secrets/ssh/client/known_hosts").read_text().splitlines()
        # Bind p1 to the different, already generated p2 key without learning an untrusted key.
        p1 = known[0].split()
        p2 = known[1].split()
        (p / "wrong_hosts").write_text(" ".join([p1[0], *p2[1:]]) + "\n")
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "minicore-management-1",
                "python",
                "-c",
                "import asyncio,json,tempfile,pathlib; from minicore_mcp.ssh_adapter import SSHAdapter; from minicore_mcp.model import Topology; t=Topology(pathlib.Path('/app/inventory/topology.json'),pathlib.Path('/runtime/observations.json')); a=SSHAdapter(t,pathlib.Path('/run/ssh-client')); f=tempfile.NamedTemporaryFile(mode='w',delete=False); f.write(input()); f.close(); a.known_hosts=pathlib.Path(f.name); print(json.dumps(asyncio.run(a.execute('p1',{'operation':'get_routes'}))))",
            ],
            input=(p / "wrong_hosts").read_text(),
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert proc.returncode == 0, proc.stderr
        c.bad_host = json.loads(proc.stdout)


@then("it returns host_key_mismatch without collecting node evidence")
def mismatch(c):
    assert c.bad_host["error_code"] == "host_key_mismatch" and c.bad_host["data"] is None


@when("a client requests arbitrary shell execution or configuration through the diagnostic key")
def bad_commands(c):
    def ssh(command, payload):
        args = [
            "docker",
            "exec",
            "-i",
            "minicore-management-1",
            "ssh",
            "-i",
            "/run/ssh-client/diagnostic",
            "-o",
            "UserKnownHostsFile=/run/ssh-client/known_hosts",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "BatchMode=yes",
            "diagnostic@172.30.250.11",
            command,
        ]
        return subprocess.run(args, input=payload, capture_output=True, text=True, timeout=15)

    c.shell = ssh("id", "{}")
    c.configure_attempt = ssh("minicore-dispatch", '{"operation":"configure","command":"shutdown"}')


@then("only the validating dispatcher runs and the request is rejected")
def forced(c):
    for p in [c.shell, c.configure_attempt]:
        assert json.loads(p.stdout)["status"] == "error" and "uid=" not in p.stdout


@then("forwarding and PTY requests are refused")
def no_forward(c):
    prefix = [
        "docker",
        "exec",
        "minicore-management-1",
        "ssh",
        "-i",
        "/run/ssh-client/diagnostic",
        "-o",
        "UserKnownHostsFile=/run/ssh-client/known_hosts",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "BatchMode=yes",
    ]
    p = subprocess.run(
        prefix + ["-tt", "diagnostic@172.30.250.11", "id"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert "PTY allocation request failed" in p.stderr, p.stderr
    p = subprocess.run(
        prefix
        + [
            "-o",
            "ExitOnForwardFailure=yes",
            "-R",
            "127.0.0.1:12345:127.0.0.1:22",
            "diagnostic@172.30.250.11",
            "id",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert p.returncode != 0 and "forwarding failed" in p.stderr, p.stderr


@then("the diagnostic identity cannot write the FRR configuration")
def no_write(c):
    p = subprocess.run(
        [
            "docker",
            "exec",
            "--user",
            "diagnostic",
            "minicore-p1-1",
            "test",
            "-w",
            "/etc/frr/frr.conf",
        ],
        capture_output=True,
    )
    assert p.returncode != 0
