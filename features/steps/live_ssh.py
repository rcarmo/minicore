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


@when("the external SDK starts a bounded node probe while a viewer watches activity SSE")
def live_activity(c):
    async def observe():
        observed = []
        async with httpx.AsyncClient(timeout=15) as http:
            async with http.stream(
                "GET", "http://127.0.0.1:19000/api/v1/activity/events"
            ) as response:
                assert response.status_code == 200

                async def watch():
                    started = set()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            observed.append(data)
                            started.update(
                                r["request_id"]
                                for r in data.get("active", [])
                                if r["node_id"] == "p1"
                            )
                            if any(r["request_id"] in started for r in data.get("recent", [])):
                                return

                reader = asyncio.create_task(watch())
                async with streamable_http_client("http://127.0.0.1:19000/mcp") as (read, write, _):
                    async with ClientSession(
                        read, write, read_timeout_seconds=timedelta(seconds=20)
                    ) as client:
                        await client.initialize()
                        await client.call_tool(
                            "ping", {"node_id": "p1", "destination": "10.200.9.2", "count": 2}
                        )
                await asyncio.wait_for(reader, 10)
        return observed

    c.activity_events = asyncio.run(observe())


@then("the viewer observes p1 active and then finished for the same request")
def live_activity_lifecycle(c):
    active = {
        r["request_id"] for s in c.activity_events for r in s["active"] if r["node_id"] == "p1"
    }
    finished = {
        r["request_id"] for s in c.activity_events for r in s["recent"] if r["node_id"] == "p1"
    }
    assert active & finished, c.activity_events


@then("no probe arguments or evidence payload appears in activity events")
def live_activity_metadata(c):
    text = json.dumps(c.activity_events)
    for key in ["destination", "10.200.9.2", "raw_evidence", "loss_percent", "arguments"]:
        assert key not in text


@when("a session cancels its in-flight five-packet node probe")
def cancel_real_ssh(c):
    import concurrent.futures
    import threading

    base = "http://127.0.0.1:19000/mcp"
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    r = httpx.post(
        base,
        headers=h,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "cancel-real", "version": "1"},
            },
        },
    )
    h |= {"Mcp-Session-Id": r.headers["mcp-session-id"], "MCP-Protocol-Version": "2025-03-26"}
    with concurrent.futures.ThreadPoolExecutor() as pool:
        started = threading.Event()

        def probe():
            started.set()
            return httpx.post(
                base,
                headers=h,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "ping",
                        "arguments": {"node_id": "p1", "destination": "10.200.9.2", "count": 5},
                    },
                },
                timeout=20,
            )

        task = pool.submit(probe)
        started.wait()
        time.sleep(0.4)
        c.cancelled_ssh_processes = diagnostic_processes()
        assert c.cancelled_ssh_processes, "probe SSH process was not observed before cancellation"
        cancel = httpx.post(
            base,
            headers=h,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 2},
            },
        )
        assert cancel.status_code == 202
        c.cancelled_real = task.result().json()
    httpx.delete(base, headers=h)


@then("that call is cancelled and its activity is cleared")
def real_cancelled(c):
    assert c.cancelled_real["error"]["code"] == -32800, c.cancelled_real
    snapshot = httpx.get("http://127.0.0.1:19000/api/v1/activity").json()
    assert not any(r["node_id"] == "p1" for r in snapshot["active"])


@then("a separate route request still succeeds")
def route_after_cancel(c):
    r = httpx.get("http://127.0.0.1:19000/api/v1/nodes/p1/routes", timeout=20)
    assert r.status_code == 200 and r.json()["status"] == "ok"


def diagnostic_processes():
    # PID plus start time avoids mistaking a new observer process for a leak.
    code = """import json,pathlib
found=[]
for entry in pathlib.Path('/proc').iterdir():
 if not entry.name.isdigit(): continue
 try:
  args=(entry/'cmdline').read_bytes().split(b'\\0')
  if args and args[0] in (b'ssh',b'/usr/bin/ssh') and b'diagnostic@172.30.250.11' in args:
   stat=(entry/'stat').read_text().rsplit(')',1)[1].split()
   found.append([entry.name,stat[19]])
 except (FileNotFoundError,ProcessLookupError): pass
print(json.dumps(found))
"""
    p = subprocess.run(
        ["docker", "exec", "minicore-management-1", "python", "-c", code],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    return {tuple(row) for row in json.loads(p.stdout)}


@then("no local diagnostic SSH process remains after cancellation")
def no_local_ssh(c):
    deadline = time.monotonic() + 3
    remaining = c.cancelled_ssh_processes
    while remaining and time.monotonic() < deadline:
        remaining &= diagnostic_processes()
        if remaining:
            time.sleep(0.1)
    assert not remaining, f"pre-cancellation SSH processes remain: {remaining}"


@when("the adapter attempts p1 with a wrong diagnostic private key")
def wrong_private_key(c):
    code = """import asyncio,json,tempfile,pathlib,subprocess
from minicore_mcp.ssh_adapter import SSHAdapter
from minicore_mcp.model import Topology
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d);subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(p/'wrong')],check=True)
 t=Topology(pathlib.Path('/app/inventory/topology.json'),pathlib.Path('/runtime/observations.json'))
 a=SSHAdapter(t,pathlib.Path('/run/ssh-client'));a.key=p/'wrong'
 print(json.dumps(asyncio.run(a.execute('p1',{'operation':'get_routes'}))))
"""
    p = subprocess.run(
        ["docker", "exec", "minicore-management-1", "python", "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert p.returncode == 0, p.stderr
    c.bad_key = json.loads(p.stdout)


@then("the result reports ssh_authentication_failed with no route evidence")
def bad_private_result(c):
    assert (
        c.bad_key["error_code"] == "ssh_authentication_failed"
        and c.bad_key["data"] is None
        and not c.bad_key["raw_evidence"]
    )


@when("the official Operator SDK collects the first customer prefix across six routers")
def live_routing(c):
    async def collect():
        token = json.loads((ROOT / "secrets/http/mcp-tokens.json").read_text())["operator"]
        async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}) as http:
            async with streamable_http_client("http://127.0.0.1:19000/mcp", http_client=http) as (
                read,
                write,
                _,
            ):
                async with ClientSession(
                    read, write, read_timeout_seconds=timedelta(seconds=30)
                ) as client:
                    await client.initialize()
                    return await client.call_tool(
                        "get_evidence", {"kind": "routing", "prefix": "10.200.8.0/29"}
                    )

    c.routing = asyncio.run(collect())


@then("all routing observations contain exact BGP, RIB and kernel evidence")
def live_routing_exact(c):
    assert not c.routing.isError, c.routing
    c.routing_value = c.routing.structuredContent
    assert json.loads(c.routing.content[0].text) == c.routing_value
    assert c.routing_value["data"]["collected"] == 6, c.routing_value
    for node in c.routing_value["data"]["nodes"]:
        data = node["data"]
        assert (
            data["prefix"] == "10.200.8.0/29"
            and data["bgp"]["paths"]
            and data["rib"]["10.200.8.0/29"]
            and data["fib"]
        ), node
        assert (
            node["source"] == "node_dispatcher" and node["collected_at"] and not node["truncated"]
        )


@then("each peer export has sender provenance and received routes remain uncollected")
def live_exports(c):
    for node in c.routing_value["data"]["nodes"]:
        data = node["data"]
        assert data["advertised"] and all(
            a["source"] == "advertised_by_node" for a in data["advertised"]
        )
        assert data["received"]["status"] == "not_collected"


@then("HTTP exposes the same exact-prefix semantics without controller ground truth")
def routing_http(c):
    response = httpx.get("http://127.0.0.1:19000/api/v1/routing?prefix=10.200.8.0%2F29", timeout=30)
    assert response.status_code == 200
    value = response.json()
    assert value["data"]["collected"] == 6 and "controller" not in value
    for node in value["data"]["nodes"]:
        other = next(n for n in c.routing_value["data"]["nodes"] if n["node_id"] == node["node_id"])
        assert set(node["data"]["rib"]) == set(other["data"]["rib"])
        assert [a["peer"] for a in node["data"]["advertised"]] == [
            a["peer"] for a in other["data"]["advertised"]
        ]
