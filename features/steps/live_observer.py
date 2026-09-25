import asyncio
import json
from pathlib import Path

from behave import then, when

ROOT = Path(__file__).resolve().parents[2]


@when("the asyncio host observer reads the running eight-node lab")
def host_live(c):
    from minicore_mcp.observer_host import collect_interfaces

    inventory = json.loads((ROOT / "inventory/topology.json").read_text())
    c.observer_live = asyncio.run(collect_interfaces(inventory))


@then("all eighteen data endpoints have fresh mapped counters and no management interface")
def all_mapped(c):
    assert len(c.observer_live) == 8 and all("data" in row for row in c.observer_live.values()), (
        c.observer_live
    )
    rows = [
        interface for row in c.observer_live.values() for interface in row["data"]["interfaces"]
    ]
    assert len(rows) == 18 and all(
        row["interface"].startswith("to-") and row["tx_packets"] >= 0 for row in rows
    ), rows


@then("public counter records contain no container identities or raw command output")
def no_internal(c):
    from minicore_mcp.observer import Store

    store = Store("minicore-local", 1)
    for node, row in c.observer_live.items():
        store.put(
            f"node:{node}:interfaces",
            row["data"],
            acquired=row["acquired"],
            incarnation=row["incarnation"],
        )
    for node in c.observer_live:
        response = store.snapshot(f"node:{node}:interfaces")
        assert response["records"]
        body = json.dumps(response["records"][0]["data"])
        assert "_internal" not in body and "container_id" not in body and "raw_evidence" not in body


@when("two host interface samples bracket a bounded endpoint probe")
def counter_probe(c):
    from minicore_mcp.observer_host import collect_interfaces, run_command

    inventory = json.loads((ROOT / "inventory/topology.json").read_text())

    async def run():
        before = await collect_interfaces(inventory)
        await run_command(
            ["docker", "exec", "minicore-host1-1", "ping", "-c", "2", "-W", "1", "10.200.8.3"]
        )
        after = await collect_interfaces(inventory)
        return before, after

    c.counter_before, c.counter_after = asyncio.run(run())


@then("endpoint transmit and receive packet deltas increase without negative counters")
def counter_direction(c):
    before = c.counter_before["host1"]["data"]["interfaces"][0]
    after = c.counter_after["host1"]["data"]["interfaces"][0]
    assert (
        after["tx_packets"] - before["tx_packets"] >= 2
        and after["rx_packets"] - before["rx_packets"] >= 2
    ), (before, after)
    assert c.counter_before["host1"]["incarnation"] == c.counter_after["host1"]["incarnation"]


@when("the deployed observer sources have collected router and endpoint data")
def live_service_ready(c):
    import time

    import httpx

    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        r = httpx.get(
            "http://127.0.0.1:19000/api/v1/observer?scope=node&node_id=p1&kind=routing", timeout=10
        )
        c.live_observation = r.json()
        if (
            r.status_code == 200
            and c.live_observation.get("records")
            and c.live_observation.get("source_health") == "ok"
        ):
            return
        time.sleep(1)
    raise AssertionError(c.live_observation)


@then("real HTTP node and link scopes return bounded current counters and routing sources")
def live_scopes(c):
    import httpx

    for query in [
        "scope=node&node_id=host1&kind=interfaces",
        "scope=node&node_id=p1&kind=routing",
        "scope=link&link_id=p1-p2&kind=interfaces",
    ]:
        r = httpx.get("http://127.0.0.1:19000/api/v1/observer?" + query, timeout=10)
        value = r.json()
        assert r.status_code == 200 and value["source_health"] == "ok" and value["records"], value
        assert len(r.content) <= 65536 and all(
            0 <= row["remaining_ms"] <= 60000 for row in value["records"]
        )
        assert r.headers["cache-control"] == "no-store" and "raw_evidence" not in r.text


@then("an official Operator MCP read returns the same observer contract with no raw evidence")
def live_mcp_observer(c):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def run():
        async with streamable_http_client("http://127.0.0.1:19000/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                value = await session.call_tool(
                    "get_evidence",
                    {
                        "kind": "observer",
                        "scope": "node",
                        "node_id": "p1",
                        "observation": "routing",
                    },
                )
                assert not value.isError, value
                data = value.structuredContent["data"]
                assert data["records"] and data["window_seconds"] == 60
                assert (
                    value.structuredContent["raw_evidence"] == ""
                    and json.loads(value.content[0].text) == value.structuredContent
                )

    asyncio.run(run())


@then(
    "the host socket directory contains only a Unix socket and the observer process cannot swap or dump core"
)
def live_no_files(c):
    import subprocess

    directory = ROOT / "runtime/observer-socket"
    assert {p.name for p in directory.iterdir()} == {"counters.sock"} and (
        directory / "counters.sock"
    ).is_socket()
    properties = subprocess.check_output(
        [
            "systemctl",
            "--user",
            "show",
            "minicore-observer.service",
            "-p",
            "MemorySwapMax",
            "-p",
            "LimitCORE",
        ],
        text=True,
    )
    assert "MemorySwapMax=0" in properties and "LimitCORE=0" in properties, properties
