import asyncio
import importlib.util
import json
import os

from behave import given, then, when


def api():
    assert importlib.util.find_spec("minicore_mcp.observer_service") is not None, (
        "observer source service unavailable"
    )
    from minicore_mcp.observer_service import CounterService, HostClient, collect_router

    return CounterService, HostClient, collect_router


@given("a host counter service with recorded inventory mappings")
def socket_fixture(c):
    CounterService, _, _ = api()
    c.obs_time = 100.0
    c.host = CounterService(
        c.inventory, c.root / "observer.sock", allowed_uid=os.getuid(), clock=lambda: c.obs_time
    )
    c.host.ingest(
        {
            "p1": {
                "acquired": 100.0,
                "incarnation": "container-private-id:99",
                "data": {
                    "interfaces": [
                        {"interface": "to-p2", "state": "UP", "tx_packets": 2, "rx_packets": 1}
                    ]
                },
            }
        }
    )


@when("a permitted client reads an inventoried node scope")
def permitted_socket(c):
    async def run():
        _, HostClient, _ = api()
        await c.host.start(collect=False)
        try:
            c.socket_value = await HostClient(c.root / "observer.sock").read("p1")
        finally:
            await c.host.close()

    asyncio.run(run())


@then("it receives typed counters and the original acquisition time with no container ID")
def socket_counters(c):
    assert (
        c.socket_value["data"]["interfaces"][0]["tx_packets"] == 2
        and c.socket_value["acquired"] == 100.0
    )
    assert "container-private-id" not in json.dumps(c.socket_value)


@when("clients send unknown nodes or extra command fields")
def invalid_socket(c):
    async def run():
        c.denials = []
        await c.host.start(collect=False)
        try:
            for value in [{"node_id": "management"}, {"node_id": "p1", "command": "id"}]:
                r, w = await asyncio.open_unix_connection(str(c.root / "observer.sock"))
                w.write(json.dumps(value).encode() + b"\n")
                await w.drain()
                c.denials.append(json.loads(await r.readline()))
                w.close()
                await w.wait_closed()
        finally:
            await c.host.close()

    asyncio.run(run())


@then("the host rejects every request without invoking a collector")
def socket_denials(c):
    assert all(row.get("error_code") == "invalid_scope" for row in c.denials)


@when("a client reads after the host sample has expired")
def old_socket(c):
    c.obs_time = 160.0
    permitted_socket(c)


@then("no stale counter sample reaches management")
def no_old_socket(c):
    assert c.socket_value["data"] is None and c.socket_value["error_code"] == "source_unavailable"


@when("the Unix peer is not the permitted management identity")
def wrong_peer(c):
    c.host.allowed_uid = os.getuid() + 99
    permitted_socket(c)


@then("no counter data is returned")
def no_peer(c):
    assert c.socket_value.get("data") is None and c.socket_value["error_code"] == "denied_identity"


@given("a recording bounded SSH adapter with BGP RIB FIB and neighbor replies")
def routing_source(c):
    class Adapter:
        def __init__(self):
            self.calls = []

        async def execute(self, node, args):
            self.calls.append((node, args))
            prefix = args["prefix"]
            return {
                "error_code": None,
                "data": {
                    "prefix": prefix,
                    "bgp": {
                        "prefix": prefix,
                        "paths": [{"valid": True, "nexthops": [{"ip": "10.200.1.2"}]}],
                    },
                    "rib": {prefix: [{"nexthops": [{"ip": "10.200.1.2"}]}]},
                    "fib": [{"dst": prefix, "gateway": "10.200.1.2"}],
                    "bgp_peers": {
                        "ipv4Unicast": {
                            "peers": {
                                "10.254.0.2": {"state": "Established", "secret-extra": "ignore"}
                            }
                        }
                    },
                    "ospf_neighbors": {"10.254.0.2": [{"nbrState": "Full/-"}]},
                    "raw": "do not store",
                },
                "raw_evidence": "payload to exclude",
            }

    c.router_adapter = Adapter()


@when("the async observer collects one router routing scope")
def collect_scope(c):
    _, _, collect_router = api()
    c.routing_scope = asyncio.run(collect_router(c.topology, c.router_adapter, "p1"))


@then("only network peer prefix and next-hop fields are stored without raw output")
def stripped_scope(c):
    from minicore_mcp.observer import validate

    value = c.routing_scope[0]
    validate("routing", value)
    assert {r["source"] for r in value["routes"]} == {"bgp", "rib", "fib"} and len(
        c.router_adapter.calls
    ) == 2
    assert "secret-extra" not in json.dumps(value) and "payload" not in json.dumps(value)
