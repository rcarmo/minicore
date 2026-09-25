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
