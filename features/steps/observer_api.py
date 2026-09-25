import asyncio
import json

from behave import given, then, when
from umcp_shared import MCPRequestContext


def http(c, query):
    return asyncio.run(
        c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/observer?" + query,
            headers={"authorization": "Bearer " + "o" * 40},
            body=b"",
            peer="127.0.0.1",
        )
    )


@given("a populated volatile observer service")
def populated_observer(c):
    from minicore_mcp.observer import Store

    assert hasattr(c.server, "observer"), "observer API contract is unavailable"
    c.obs_now = 100.0
    c.obs = Store("minicore-local", c.generation, clock=lambda: c.obs_now)
    c.obs.put(
        "node:p1:interfaces",
        {"interfaces": [{"interface": "to-p2", "state": "UP", "tx_packets": 2, "rx_packets": 2}]},
        acquired=100,
        incarnation="p1-test",
    )
    c.server.observer = c.obs


@when("Operator reads node p1 observer interfaces through HTTP and MCP")
def observer_parity(c):
    c.obs_http = http(c, "scope=node&node_id=p1&kind=interfaces")
    context = MCPRequestContext(
        transport="streamable-http",
        principal="operator",
        headers={"authorization": "Bearer " + "o" * 40},
    )
    c.obs_mcp = asyncio.run(
        c.server.process_request_async(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "get_evidence",
                        "arguments": {
                            "kind": "observer",
                            "scope": "node",
                            "node_id": "p1",
                            "observation": "interfaces",
                        },
                    },
                }
            ),
            context=context,
        )
    )


@then("both transports return the same records without starting a collector")
def same_observer(c):
    assert c.obs_http.status == 200, c.obs_http.body
    left = json.loads(c.obs_http.body)
    right = c.obs_mcp["result"]["structuredContent"]["data"]
    assert left == right and left["records"] and c.server.adapter is None


@then("replies disable HTTP caching and exclude raw output and controller state")
def cache_safe(c):
    assert ("Cache-Control", "no-store") in c.obs_http.headers
    assert (
        "raw_evidence" not in c.obs_http.body.decode()
        and "controller" not in c.obs_http.body.decode()
    )


@when('the observer API receives "{query}"')
def invalid_observer(c, query):
    c.obs_http = http(c, query)


@then("the observer request is rejected without opening a source")
def denied_observer(c):
    assert c.obs_http.status == 400 and c.server.adapter is None


@when("the populated observer ages beyond sixty seconds")
def age_observer(c):
    c.obs_now = 160
    c.obs_http = http(c, "scope=node&node_id=p1&kind=interfaces")


@then("HTTP returns an empty window instead of repeating the previous record")
def empty_observer(c):
    assert (
        c.obs_http.status == 200
        and json.loads(c.obs_http.body)["records"] == []
        and c.obs.record_count == 0
    )


@when("the observer event stream is read and then the credential is revoked")
def stream_observer(c):
    async def run():
        response = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/observer/events",
            headers={"authorization": "Bearer " + "o" * 40},
            body=b"",
            peer="127.0.0.1",
        )
        assert response.status == 200 and response.stream
        c.obs_event = await anext(response.stream)
        c.tokens.write_text(json.dumps({"operator": "x" * 40, "god": "g" * 40}))
        try:
            await anext(response.stream)
        except StopAsyncIteration:
            c.obs_stream_closed = True
        else:
            c.obs_stream_closed = False
        await response.stream.aclose()

    asyncio.run(run())


@then("only an epoch and revision invalidation is sent and the stream releases its slot")
def stream_safe(c):
    data = json.loads(c.obs_event.decode().split("data: ", 1)[1].strip())
    assert (
        set(data) == {"observer_epoch", "generation", "revision"}
        and c.obs_stream_closed
        and c.server.streams == 0
    )


@when("the lab generation changes before an observer read")
def changed_generation(c):
    c.topology.inventory["generation"] += 1
    c.obs_http = http(c, "scope=node&node_id=p1&kind=interfaces")


@then("all previous records and baselines are invalidated before the response")
def changed_empty(c):
    result = json.loads(c.obs_http.body)
    assert result["generation"] == c.generation + 1 and result["records"] == []
