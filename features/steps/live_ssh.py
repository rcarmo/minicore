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


@when("the official MCP client invokes inventory, interfaces, routes, BGP, OSPF and ping")
def all_live_tools(c):
    async def call():
        async with streamable_http_client("http://127.0.0.1:19000/mcp") as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=20)
            ) as client:
                await client.initialize()
                results = {}
                cases = [
                    ("inventory", "list_nodes", {}),
                    ("interfaces", "get_interfaces", {"node_id": "p1"}),
                    ("routes", "get_routes", {"node_id": "p1"}),
                    ("bgp", "get_neighbors", {"node_id": "p1", "protocol": "bgp"}),
                    ("ospf", "get_neighbors", {"node_id": "p1", "protocol": "ospf"}),
                    ("probe", "ping", {"node_id": "p1", "destination": "10.200.1.3", "count": 2}),
                ]
                for key, tool, args in cases:
                    results[key] = await client.call_tool(tool, args)
                results["loss"] = await client.call_tool(
                    "ping", {"node_id": "p1", "destination": "10.200.9.2", "count": 2}
                )
                # The Docker-reserved unused address is not inventory-approved; invalid targets are denied.
                try:
                    results["denied"] = await client.call_tool(
                        "ping", {"node_id": "p1", "destination": "172.30.250.2", "count": 1}
                    )
                except Exception as exc:
                    results["denied"] = str(exc)
                return results

    c.live = asyncio.run(call())


@then("every call returns observed evidence with matching text and structured data")
def all_results(c):
    for key, result in c.live.items():
        if key == "denied":
            continue
        assert result.isError is False, (key, result)
        assert json.loads(result.content[0].text) == result.structuredContent
        assert result.structuredContent["status"] == "ok"


@then("interfaces expose only data interfaces rather than management state")
def only_data(c):
    names = {e["ifname"] for e in c.live["interfaces"].structuredContent["data"]}
    assert names == {"to-p2", "to-pe1", "to-pe2"}, names


@then("an adjacent-router probe returns sent, received, loss and RTT measurements")
def healthy_probe(c):
    data = c.live["probe"].structuredContent["data"]
    assert (
        data["sent"] == data["received"] == 2
        and data["loss_percent"] == 0
        and data["rtt_ms"]["avg"] >= 0
    )


@then(
    "a customer-endpoint probe without a return route reports measured loss rather than a transport failure"
)
def probe_failure(c):
    result = c.live["loss"]
    assert result.isError is False
    data = result.structuredContent["data"]
    assert (
        data["sent"] == 2
        and data["received"] == 0
        and data["loss_percent"] == 100.0
        and data["rtt_ms"] is None
    )


@then("an unapproved management destination is denied before SSH execution")
def denied_probe(c):
    assert "denied_destination" in c.live["denied"]


@when("the official client reads provider adjacencies and a customer's undeclared OSPF")
def protocol_states(c):
    async def call():
        async with streamable_http_client("http://127.0.0.1:19000/mcp") as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=20)
            ) as client:
                await client.initialize()
                return {
                    key: await client.call_tool(
                        "get_neighbors", {"node_id": node, "protocol": protocol}
                    )
                    for key, node, protocol in [
                        ("ospf", "p1", "ospf"),
                        ("bgp", "p1", "bgp"),
                        ("disabled", "ce1", "ospf"),
                    ]
                }

    c.protocols = asyncio.run(call())


@then("the provider evidence contains Full neighbors and Established BGP peers")
def protocol_evidence(c):
    ospf = c.protocols["ospf"].structuredContent["data"]
    assert any(
        "Full" in p["nbrState"] for group in ospf.get("neighbors", ospf).values() for p in group
    )
    bgp = c.protocols["bgp"].structuredContent["data"]
    assert all(p["state"] == "Established" for p in bgp["ipv4Unicast"]["peers"].values())


@then("the customer OSPF request reports protocol_not_enabled")
def protocol_disabled(c):
    r = c.protocols["disabled"]
    assert r.isError and r.structuredContent["error_code"] == "protocol_not_enabled", r
