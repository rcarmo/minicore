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
        assert r["result"]["isError"] == (name != "list_nodes")
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


@when("authenticated Operator and God clients exercise all nine known tools")
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
            assert data["result"]["isError"] == (name not in {"list_nodes", "list_fault_scenarios"})
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
