import json
import secrets
import time

from behave import given, then, when
from mcp_harness.wire import ARGS, GOD, OPERATOR, Wire


def wire(c, ttl=1800):
    c.mcp = Wire(ttl)
    c.add_cleanup(c.mcp.close)
    return c.mcp


@when('an independent wire client negotiates "{version}"')
def negotiate(c, version):
    w = wire(c)
    c.sid, c.version = w.initialize(version=version)
    assert c.version == version


@then(
    "initialized, discovery, schema annotations, tool results and session deletion obey that protocol"
)
def lifecycle(c):
    w = c.mcp
    kw = {"session": c.sid, "version": c.version}
    assert w.rpc("notifications/initialized", request_id=None, **kw)[0] == 202
    status, _, r = w.rpc("tools/list", **kw)
    assert status == 200
    assert {t["name"] for t in r["result"]["tools"]} == OPERATOR
    for t in r["result"]["tools"]:
        assert t["inputSchema"]["additionalProperties"] is False
        assert t["annotations"]["readOnlyHint"] is True
    for name in OPERATOR:
        status, _, r = w.rpc("tools/call", {"name": name, "arguments": ARGS.get(name, {})}, **kw)
        assert status == 200 and "result" in r, (status, r)
        assert r["result"]["isError"] == (name not in {"list_nodes", "get_evidence"})
        assert json.loads(r["result"]["content"][0]["text"]) == r["result"]["structuredContent"]
    assert w.request("DELETE", **kw)[0] == 200
    assert w.rpc("tools/list", **kw)[0] == 404


@when("an MCP session receives a missing or unsupported protocol version")
def wrong_version(c):
    w = wire(c)
    c.sid, _ = w.initialize()
    c.bad_versions = [w.rpc("tools/list", session=c.sid, version=v) for v in [None, "2099-01-01"]]


@then("the response declares the supported versions and the valid session still works")
def version_error(c):
    for status, _, data in c.bad_versions:
        assert status == 400 and set(data["supported"]) == {"2025-03-26", "2024-11-05"}
    assert c.mcp.rpc("tools/list", session=c.sid)[0] == 200


@when("a client proposes a protocol newer than the server supports")
def fallback(c):
    c.sid, c.version = wire(c).initialize(version="2099-01-01")


@then("initialization selects a supported version rather than claiming the proposed version")
def fallback_result(c):
    assert c.version in {"2025-03-26", "2024-11-05"}


@when("an authenticated client sends MCP ping")
def ping(c):
    c.response = wire(c).rpc("ping")


@then("the JSON-RPC result is an empty object and no node operation runs")
def pong(c):
    status, _, data = c.response
    assert status == 200 and data["result"] == {}, c.response


@when('a wire client sends malformed RPC case "{case}"')
def malformed(c, case):
    w = wire(c)
    cases = {
        "invalid JSON": b"{",
        "batch array": [],
        "boolean request ID": {"jsonrpc": "2.0", "id": True, "method": "tools/list"},
        "invalid version": {"jsonrpc": "1.0", "id": 1, "method": "tools/list"},
        "parameters array": {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": []},
        "tool name array": {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": ["apply_fault"]},
        },
        "tool arguments array": {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_routes", "arguments": []},
        },
        "unknown tool": {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "run_shell"},
        },
    }
    c.response = w.request("POST", payload=cases[case])


@then("the response is a bounded client error rather than a server error or dropped connection")
def client_error(c):
    status, _, data = c.response
    assert status in {200, 400, 403}, c.response
    if status == 200:
        assert data["error"]["code"] in {-32700, -32600, -32602, -32601}, data
    assert len(json.dumps(data)) < 8192


@when('a wire client sends HTTP case "{case}"')
def framing(c, case):
    w = wire(c)
    auth = "Authorization: Bearer " + w.tokens["operator"] + "\r\n"
    common = "Content-Type: application/json\r\nMCP-Protocol-Version: 2025-03-26\r\nConnection: close\r\n"
    if case == "duplicate authorization":
        c.status = w.raw(auth + auth + common + "Content-Length: 2\r\n", b"{}")
    elif case == "duplicate content length":
        c.status = w.raw(auth + common + "Content-Length: 2\r\nContent-Length: 2\r\n", b"{}")
    elif case == "transfer encoding":
        c.status = w.raw(auth + common + "Transfer-Encoding: chunked\r\n", b"0\r\n\r\n")
    elif case == "oversized body":
        c.status = w.raw(auth + common + "Content-Length: 3000000\r\n")
    else:
        extra = {
            "wrong content type": {"Content-Type": "text/plain"},
            "unsupported accept": {"Accept": "image/png"},
            "foreign origin": {"Origin": "https://evil.example"},
        }[case]
        c.status = w.rpc("tools/list", extra=extra)[0]


@then("the transport rejects the request without executing a tool")
def rejected(c):
    assert c.status in {400, 403, 406, 413, 415}, c.status


@when("an inactive session reaches its configured expiry")
def expiry(c):
    w = wire(c, 0.2)
    c.sid, _ = w.initialize()
    time.sleep(0.35)


@then("reuse returns unknown session and a fresh initialization succeeds")
def expired(c):
    assert c.mcp.rpc("tools/list", session=c.sid)[0] == 404
    c.mcp.initialize()


@when("the test service restarts with the same credentials")
def restart(c):
    w = wire(c)
    c.sid, _ = w.initialize()
    w.stop()
    w.start()


@then("the old session is rejected and reinitialization restores discovery")
def restart_ok(c):
    assert c.mcp.rpc("tools/list", session=c.sid)[0] == 404
    sid, _ = c.mcp.initialize()
    assert c.mcp.rpc("tools/list", session=sid)[0] == 200


@when("a session event stream is opened, disconnected and reconnected")
def streaming(c):
    w = wire(c)
    c.sid, _ = w.initialize()
    r, conn = w.stream(c.sid)
    assert r.status == 200 and r.readline() == b": connected\n"
    duplicate, dc = w.stream(c.sid)
    assert duplicate.status == 409
    duplicate.close()
    dc.close()
    r.close()
    conn.close()
    time.sleep(0.5)
    # Kernel disconnect detection can require more than one keepalive.
    for _ in range(20):
        r, conn = w.stream(c.sid)
        if r.status == 200:
            break
        assert r.status == 409
        r.close()
        conn.close()
        time.sleep(0.1)
    c.stream_reply = r


@then("its framing is valid, duplicate attachment is refused, and deletion closes the stream")
def stream_end(c):
    r = c.stream_reply
    assert r.status == 200
    assert r.getheader("Content-Length") is None and r.getheader("Transfer-Encoding") is None
    assert c.mcp.request("DELETE", session=c.sid)[0] == 200
    assert len(r.read()) < 65536


@when("the Operator credential is replaced and the service restarts")
def rotate(c):
    w = wire(c)
    c.sid, _ = w.initialize()
    c.old = w.tokens["operator"]
    w.stop()
    w.tokens["operator"] = secrets.token_hex(24)
    w.start()


@then(
    "old credentials fail on POST, GET and DELETE while the new credential initializes successfully"
)
def rotation_ok(c):
    for method in ["POST", "GET", "DELETE"]:
        assert (
            c.mcp.request(method, session=c.sid, extra={"Authorization": "Bearer " + c.old})[0]
            == 401
        )
    c.mcp.initialize()


@when("authenticated Operator and God clients exercise all ten known tools")
def matrix(c):
    w = wire(c)
    c.matrix = []
    for role in ["operator", "god"]:
        sid, _ = w.initialize(role)
        listed = w.rpc("tools/list", role=role, session=sid)[2]["result"]["tools"]
        assert {t["name"] for t in listed} == (OPERATOR | GOD if role == "god" else OPERATOR)
        for name in OPERATOR | GOD:
            c.matrix.append((role, name, w.call(name, role, sid)))


@then("discovery and direct calls enforce the same capability matrix")
def matrix_ok(c):
    for role, name, (status, _, data) in c.matrix:
        assert status == (403 if role == "operator" and name in GOD else 200), (
            role,
            name,
            status,
            data,
        )


@then("unavailable execution has native tool errors without credentials in responses")
def matrix_errors(c):
    for _, name, (status, _, data) in c.matrix:
        if status == 200:
            assert data["result"]["isError"] == (
                name not in {"list_nodes", "list_fault_scenarios", "get_evidence"}
            )
        for token in c.mcp.tokens.values():
            assert token not in json.dumps(data)


@when("an Operator forges role information in headers, query and tool arguments")
def forged(c):
    w = wire(c)
    c.forged = []
    for extra, path, args in [
        ({"X-Role": "god"}, "/mcp", {}),
        ({}, "/mcp?mode=god", {}),
        ({}, "/mcp", {"mode": "god", "principal": "god"}),
    ]:
        c.forged.append(
            w.request(
                "POST",
                path,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "get_fault_state", "arguments": args},
                },
                extra=extra,
            )
        )


@then("no request receives God-only results or changes generation")
def no_escalation(c):
    assert all(r[0] in {400, 403} for r in c.forged)
    assert c.mcp.request("GET", "/api/v1/topology")[2]["generation"] == 1


@when("an Operator presents a God session on POST, GET and DELETE")
def stolen(c):
    w = wire(c)
    c.sid, _ = w.initialize("god")
    c.stolen = [
        w.request(m, payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, session=c.sid)
        for m in ["POST", "GET", "DELETE"]
    ]


@then("each request is denied and the God session remains usable")
def session_owner(c):
    assert all(r[0] == 403 for r in c.stolen)
    assert c.mcp.rpc("tools/list", role="god", session=c.sid)[0] == 200


@given("two MCP sessions are executing requests with the same request ID")
def two_sessions(c):
    w = wire(c)
    c.a, _ = w.initialize()
    c.b, _ = w.initialize()
    c.first = w.slow(session=c.a)
    c.second = w.slow(session=c.b)


@when("the first session cancels its request")
def cancel_first(c):
    c.cancel_status = c.mcp.rpc(
        "notifications/cancelled", {"requestId": 10}, session=c.a, request_id=None
    )[0]


@then("only its own request is cancelled and the other completes successfully")
def isolated_cancel(c):
    assert c.cancel_status == 202
    assert c.first.result()[2]["error"]["code"] == -32800
    assert "result" in c.second.result()[2]


@given("Operator and God are executing requests with the same request ID")
def principals(c):
    w = wire(c)
    c.a, _ = w.initialize()
    c.b, _ = w.initialize("god")
    c.first = w.slow(session=c.a)
    c.second = w.slow("god", c.b)


@when("Operator cancels its request")
def operator_cancel(c):
    cancel_first(c)


@then("the God request is unaffected")
def god_unaffected(c):
    isolated_cancel(c)


@given("a request has a progress token different from its request ID")
def token(c):
    w = wire(c)
    c.a, _ = w.initialize()
    c.first = w.slow(session=c.a, meta={"progressToken": "progress-123"})


@when("cancellation names only that progress token")
def cancel_token(c):
    c.mcp.rpc(
        "notifications/cancelled", {"requestId": "progress-123"}, session=c.a, request_id=None
    )


@then("the request continues until its own request ID is cancelled")
def token_not_id(c):
    time.sleep(0.1)
    assert not c.first.done()
    assert (
        c.mcp.rpc("notifications/cancelled", {"requestId": 10}, session=c.a, request_id=None)[0]
        == 202
    )
    assert c.first.result()[2]["error"]["code"] == -32800


@given("a scoped request is already executing")
@given("a request is executing in one Operator session")
def active(c):
    w = wire(c)
    c.a, _ = w.initialize()
    c.first = w.slow(session=c.a)


@when("the same session starts another request with the same ID")
def duplicate(c):
    c.duplicate = c.mcp.call("get_routes", session=c.a)


@then("the duplicate is rejected without replacing or cancelling the first request")
def duplicate_rejected(c):
    assert c.duplicate[2]["error"]["code"] == -32600
    assert "result" in c.first.result()[2]


@when("another Operator session sends cancellation for that ID")
def foreign(c):
    c.b, _ = c.mcp.initialize()
    assert (
        c.mcp.rpc("notifications/cancelled", {"requestId": 10}, session=c.b, request_id=None)[0]
        == 202
    )


@then("the first request remains active")
def unaffected(c):
    assert "result" in c.first.result()[2]


@given("an authenticated stateless request is executing")
def stateless(c):
    c.first = wire(c).slow()


@when("a separate stateless HTTP connection sends cancellation for its ID")
def stateless_cancel(c):
    c.cancel_status = c.mcp.rpc("notifications/cancelled", {"requestId": 10}, request_id=None)[0]


@then("the cancellation is denied and the active request is unaffected")
def stateless_denied(c):
    assert c.cancel_status == 403
    unaffected(c)


@when("a client sends a non-string tool name or method")
def typed(c):
    w = wire(c)
    c.typed = [
        w.request(
            "POST", payload={"jsonrpc": "2.0", "id": 1, "method": method, "params": {"name": []}}
        )
        for method in ["tools/call", []]
    ]


@then("it receives a validation or authorization failure without HTTP 500")
def typed_ok(c):
    assert all(r[0] in {400, 403} or (r[0] == 200 and "error" in r[2]) for r in c.typed), c.typed


@when("the client sends repeated Accept fields listing JSON and event streams")
def repeated_accept(c):
    w = wire(c)
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
    c.accept_status = w.raw(
        "Authorization: Bearer "
        + w.tokens["operator"]
        + "\r\nContent-Type: application/json\r\nMCP-Protocol-Version: 2025-03-26\r\nAccept: application/json\r\naccept: text/event-stream\r\nContent-Length: "
        + str(len(body))
        + "\r\n",
        body,
    )


@then("the request succeeds while duplicated credentials remain invalid")
def accept_ok(c):
    assert c.accept_status == 200, c.accept_status
    framing(c, "duplicate authorization")
    assert c.status == 400


@when("the node dispatcher receives a valid get_routes request for an IPv4 prefix")
def dispatcher_route(c):
    from node_dispatcher import command_for, decode_request

    c.node_request = decode_request(b'{"operation":"get_routes","prefix":"10.200.8.0/29"}')
    c.node_args = command_for(c.node_request, {"destinations": [], "interfaces": []})


@then("it chooses the fixed vtysh executable and exact show route arguments without a shell")
def dispatcher_args(c):
    assert c.node_args == ["/usr/bin/vtysh", "-c", "show ip route 10.200.8.0/29 json"]


@when('the node dispatcher receives "{payload}"')
def dispatcher_bad(c, payload):
    from node_dispatcher import command_for, decode_request

    inputs = {
        "malformed JSON": b"{",
        "unknown operation": b'{"operation":"shell"}',
        "extra field": b'{"operation":"get_routes","command":"id"}',
        "external destination": b'{"operation":"ping","destination":"8.8.8.8"}',
        "shell syntax": b'{"operation":"get_routes","prefix":"$(id)"}',
        "excessive count": b'{"operation":"ping","destination":"10.200.1.3","count":6}',
        "invalid protocol": b'{"operation":"get_neighbors","protocol":"rip"}',
        "oversized stdin": b"x" * 4097,
        "non-object JSON": b"[]",
    }
    try:
        command_for(
            decode_request(inputs[payload]),
            {"destinations": ["10.200.1.3"], "interfaces": ["to-p2"]},
        )
    except ValueError:
        c.rejected = True
    else:
        c.rejected = False


@then("it rejects the payload before executing a process")
def dispatcher_rejected(c):
    assert c.rejected


@when("an exact-prefix node command returns invalid JSON")
def dispatcher_parse(c):
    from node_dispatcher import normalise

    try:
        normalise("get_routes", "broken")
    except ValueError:
        c.parse_error = True
    else:
        c.parse_error = False


@then("the dispatcher returns parse_failure rather than an empty healthy result")
def dispatcher_parse_failed(c):
    assert c.parse_error


@when("an exact-prefix node command returns an empty JSON object")
def dispatcher_empty(c):
    from node_dispatcher import normalise

    c.empty = normalise("get_routes", "{}")


@then("the dispatcher returns successful bounded raw and normalised empty data")
def dispatcher_empty_ok(c):
    assert c.empty == {}


@when("a fixed node command exceeds its deadline")
def dispatcher_timeout(c):
    import sys

    from node_dispatcher import run_bounded

    c.execution = run_bounded([sys.executable, "-c", "import time;time.sleep(2)"], deadline=0.03)


@then("the node process is killed and the response reports execution_timeout")
def dispatcher_timed_out(c):
    assert c.execution["error_code"] == "execution_timeout"


@when("a fixed node command exceeds the output cap")
def dispatcher_output(c):
    import sys

    from node_dispatcher import run_bounded

    c.execution = run_bounded([sys.executable, "-c", 'print("a"*100000)'], limit=1024)


@then("it is terminated with output_limit rather than retaining unlimited output")
def dispatcher_capped(c):
    assert c.execution["error_code"] == "output_limit" and len(c.execution["stdout"]) <= 1024


@when("the node dispatcher source is compiled and its denied command entrypoint is invoked")
def compiled_dispatcher(c):
    import os
    import subprocess
    import sys
    from pathlib import Path

    path = Path("router-image/dispatcher/node_dispatcher.py")
    c.compiled = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)], capture_output=True, text=True
    )
    c.denied_entry = subprocess.run(
        [sys.executable, str(path)],
        input="{}",
        env=os.environ | {"SSH_ORIGINAL_COMMAND": "id"},
        capture_output=True,
        text=True,
        timeout=5,
    )


@then("it produces a bounded JSON denial without a Python traceback")
def entrypoint_valid(c):
    assert c.compiled.returncode == 0, c.compiled.stderr
    assert c.denied_entry.returncode == 0, c.denied_entry.stderr
    assert json.loads(c.denied_entry.stdout)["status"] == "error"
    assert "Traceback" not in c.denied_entry.stderr


@when("an OSPF query is requested on a node without declared OSPF")
def disabled_ospf(c):
    from node_dispatcher import command_for

    try:
        command_for(
            {"operation": "get_neighbors", "protocol": "ospf"},
            {"protocols": ["bgp"], "interfaces": [], "destinations": []},
        )
    except ValueError as e:
        c.disabled_protocol = str(e)
    else:
        c.disabled_protocol = None


@then(
    "the dispatcher reports protocol_not_enabled without interpreting an empty response as healthy neighbors"
)
def disabled_ospf_result(c):
    assert c.disabled_protocol == "protocol_not_enabled"


@when("an authorised node-directed MCP request begins and finishes")
def activity_execution(c):
    import asyncio

    from umcp_shared import MCPRequestContext

    class Slow:
        async def execute(self, node, request):
            await asyncio.sleep(0.1)
            return {
                "status": "ok",
                "error_code": None,
                "data": {},
                "raw_evidence": "",
                "duration_ms": 1,
                "truncated": False,
            }

    c.server.adapter = Slow()

    async def execute():
        task = asyncio.create_task(
            c.server.process_request_async(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "get_routes", "arguments": {"node_id": "p1"}},
                    }
                ),
                context=MCPRequestContext(
                    principal="operator", headers={"authorization": "Bearer " + "o" * 40}
                ),
            )
        )
        await asyncio.sleep(0.03)
        c.during = c.server.activity.snapshot(c.generation)
        await task
        c.after = c.server.activity.snapshot(c.generation)

    asyncio.run(execute())


@then("its node is active during execution and inactive after completion")
def activity_transition(c):
    assert [r["node_id"] for r in c.during["active"]] == ["p1"] and c.after["active"] == []


@then("the activity response contains no arguments, result bodies or credentials")
def activity_minimal(c):
    text = json.dumps(c.during)
    for value in ["arguments", "raw_evidence", "authorization", "o" * 40]:
        assert value not in text


@when("two ordinary requests overlap on p1")
def activity_overlap(c):
    c.a = c.server.activity.start("p1", c.generation)
    c.b = c.server.activity.start("p1", c.generation)


@then("finishing one retains p1 activity until the other finishes")
def activity_overlap_result(c):
    c.server.activity.finish(c.a)
    assert len(c.server.activity.snapshot(c.generation)["active"]) == 1
    c.server.activity.finish(c.b)
    assert c.server.activity.snapshot(c.generation)["active"] == []


@when('a node request ends by "{outcome}"')
def activity_end(c, outcome):
    import asyncio

    from umcp_shared import MCPRequestContext

    class Fails:
        async def execute(self, node, request):
            if outcome == "cancellation":
                raise asyncio.CancelledError()
            raise RuntimeError("fixture error")

    c.server.adapter = None if outcome == "backend_not_configured" else Fails()

    async def execute():
        try:
            await c.server.process_request_async(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "get_routes", "arguments": {"node_id": "p1"}},
                    }
                ),
                context=MCPRequestContext(
                    principal="operator", headers={"authorization": "Bearer " + "o" * 40}
                ),
            )
        except RuntimeError:
            pass

    asyncio.run(execute())


@then("its active record is removed without a health-state change")
def activity_end_result(c):
    assert c.server.activity.snapshot(c.generation)["active"] == [] and all(
        n["state"] == "unknown" for n in c.topology.snapshot()["nodes"]
    )


@when('"{kind}" occurs')
def no_activity_operation(c, kind):
    import asyncio

    from umcp_shared import MCPRequestContext

    async def execute():
        if kind in ["browser routes", "background snapshot"]:
            await c.server.handle_http_request_async(
                method="GET",
                path="/api/v1/nodes/p1/routes" if kind == "browser routes" else "/api/v1/topology",
                headers={"authorization": "Bearer " + "o" * 40},
                body=b"",
                peer="127.0.0.1",
            )
            return
        calls = {
            "list_nodes": ("operator", "list_nodes", {}),
            "denied God call": ("operator", "get_fault_state", {}),
            "invalid node": ("operator", "get_routes", {"node_id": "alien"}),
            "God mutation": ("god", "reset_lab", {"idempotency_key": "activity-test"}),
        }
        role, name, args = calls[kind]
        await c.server.process_request_async(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": args},
                }
            ),
            context=MCPRequestContext(
                principal=role, headers={"authorization": "Bearer " + role[0] * 40}
            ),
        )

    asyncio.run(execute())


@then("no node activity record is published")
def activity_excluded(c):
    assert c.server.activity.snapshot(c.generation)["revision"] == 0


@when("an Operator opens the activity snapshot and stream")
def activity_stream(c):
    import asyncio

    async def execute():
        c.snapshot_reply = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/activity",
            headers={"authorization": "Bearer " + "o" * 40},
            body=b"",
            peer="127.0.0.1",
        )
        r = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/activity/events",
            headers={"authorization": "Bearer " + "o" * 40},
            body=b"",
            peer="127.0.0.1",
        )
        c.stream_first = await anext(r.stream)
        await r.stream.aclose()
        c.denied_reply = await c.server.handle_http_request_async(
            method="GET", path="/api/v1/activity", headers={}, body=b"", peer="127.0.0.1"
        )

    asyncio.run(execute())


@then("the stream begins with bounded active-state metadata and releases its slot on close")
def activity_stream_result(c):
    assert (
        c.snapshot_reply.status == 200
        and b"activity.snapshot" in c.stream_first
        and c.server.streams == 0
    )


@then("an unauthenticated viewer cannot read activity in the authenticated profile")
def activity_auth(c):
    assert c.denied_reply.status == 401


@when("the lab generation changes with old activity still recorded")
def activity_generation(c):
    c.server.activity.start("p1", c.generation)
    c.new = c.server.activity.snapshot(c.generation + 1)


@then("the next snapshot excludes old-generation activity")
def activity_generation_result(c):
    assert c.new["active"] == [] and c.new["generation"] == c.generation + 1


@when("more than the activity cap is recorded and time advances past the request lease")
def activity_expire(c):
    from unittest.mock import patch

    with patch("minicore_mcp.activity.time.time", return_value=1000):
        for _ in range(140):
            c.server.activity.start("p1", c.generation)
        c.bounded = c.server.activity.snapshot(c.generation)
    with patch("minicore_mcp.activity.time.time", return_value=1030):
        c.expired = c.server.activity.snapshot(c.generation)


@then("the snapshot stays bounded and abandoned active records disappear")
def activity_bound(c):
    assert len(c.bounded["active"]) <= 128 and c.expired["active"] == []
