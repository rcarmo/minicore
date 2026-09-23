import asyncio
import base64
import copy
import http.client
import json
from datetime import datetime, timedelta, timezone

from behave import given, then, when
from minicore_mcp.model import Topology, utc_now
from minicore_mcp.policy import GOD, OPERATOR, Policy
from umcp_shared import MCPHTTPResponse, MCPRequestContext, validate_http_response


def run(coroutine):
    return asyncio.run(coroutine)


def headers(role):
    return {} if role == "anonymous" else {"authorization": "Bearer " + role[0] * 40}


def rpc(c, role, method, params=None):
    return run(
        c.server.process_request_async(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}),
            context=MCPRequestContext(
                transport="streamable-http", principal=role, headers=headers(role)
            ),
        )
    )


def observations(c, **changes):
    payload = {
        "lab_id": c.inventory["lab_id"],
        "generation": c.generation,
        "collected_at": utc_now(),
        "nodes": {"p1": {"container_state": "running"}, "p2": {"container_state": "exited"}},
    } | changes
    c.topology.observations.write_text(json.dumps(payload))


def logs(c, **changes):
    stamp = utc_now()
    data = {
        "schema_version": "1.0",
        "lab_id": c.inventory["lab_id"],
        "generation": c.generation,
        "node_id": "p1",
        "source": "container",
        "collected_at": stamp,
        "window_start": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
        "status": "ok",
        "error_code": None,
        "truncated": False,
        "entries": [
            {
                "id": f"{i:024x}",
                "timestamp": stamp,
                "source": "container",
                "severity": "unknown",
                "message": f"event {i}",
                "truncated": False,
            }
            for i in range(5)
        ],
    } | changes
    c.logfile.write_text(json.dumps(data))
    return data


@given("an isolated management service with Operator and God credentials")
def isolated(c):
    assert set(c.policy.credentials) == {"operator", "god"}


@when('"{role}" requests tool discovery')
def discover(c, role):
    c.role = role
    c.result = rpc(c, role, "tools/list")


@then('exactly "{count}" tools are exposed for that role')
def tools(c, count):
    names = {t["name"] for t in c.result["result"]["tools"]}
    assert names == (OPERATOR | GOD if c.role == "god" else OPERATOR)
    assert len(names) == int(count)


@then("every tool has explicit read-only and destructive annotations")
def annotations(c):
    for t in c.result["result"]["tools"]:
        mutate = t["name"] in {"apply_fault", "reset_lab"}
        assert t["annotations"]["readOnlyHint"] is not mutate
        assert t["annotations"]["destructiveHint"] is mutate


@when('"{role}" calls "{tool}" with arguments "{args}"')
@when('"{role}" calls "{tool}" with arguments \'{args}\'')
def call(c, role, tool, args):
    c.result = rpc(c, role, "tools/call", {"name": tool, "arguments": json.loads(args)})


@then('the RPC error is "{error}"')
def rpc_error(c, error):
    assert c.result["error"]["message"] == error, c.result


@then("the topology generation remains unchanged")
def generation(c):
    assert c.topology.snapshot()["generation"] == c.generation


@when('authentication is attempted with "{identity}"')
def auth(c, identity):
    choices = {
        "missing": {},
        "bad bearer": {"authorization": "Bearer bad"},
        "malformed basic": {"authorization": "Basic !!!"},
        "forged role header": {"X-Role": "god"},
        "invalid god basic": {
            "authorization": "Basic " + base64.b64encode(("god:" + "bad").encode()).decode()
        },
        "operator basic": {
            "authorization": "Basic " + base64.b64encode(("operator:" + "o" * 40).encode()).decode()
        },
    }
    c.principal = c.policy.authenticate(choices[identity])


@then("no principal is authenticated")
def no_principal(c):
    assert c.principal is None


@given("the explicit private profile is selected")
def private(c):
    c.policy = Policy("private", c.tokens)


@when("an anonymous request is authenticated")
def anonymous(c):
    c.principal = c.policy.authenticate({})


@then("its only role is Operator")
def operator(c):
    assert c.principal.roles == ("operator",)


@then("a supplied invalid credential is not downgraded to anonymous")
def no_downgrade(c):
    assert c.policy.authenticate({"authorization": "Bearer bad"}) is None


@when('the credential configuration is "{config}"')
def configuration(c, config):
    profiles = {"bad profile": "bogus"}
    if config == "missing":
        c.tokens.unlink()
    else:
        data = {
            "identical keys": {"operator": "x" * 40, "god": "x" * 40},
            "short key": {"operator": "short"},
            "unknown role": {"admin": "x" * 40},
            "bad profile": {"operator": "x" * 40},
        }[config]
        c.tokens.write_text(json.dumps(data))
    try:
        Policy(profiles.get(config, "authenticated"), c.tokens)
    except ValueError:
        c.validation_failed = True
    else:
        c.validation_failed = False


@then("service policy construction fails")
@then("inventory validation fails")
def construction_failure(c):
    assert c.validation_failed


@then("the tool succeeds with eight expected nodes")
def inventory_result(c):
    r = c.result["result"]
    assert r["isError"] is False
    nodes = r["structuredContent"]["data"]["nodes"]
    assert len(nodes) == 8 and all(n["expected"] for n in nodes)
    assert all(n["state"] == "unknown" for n in nodes)


@then("structured and text evidence are identical")
def parity(c):
    r = c.result["result"]
    assert json.loads(r["content"][0]["text"]) == r["structuredContent"]


@then("every result carries correlation and generation metadata")
def envelope(c):
    r = c.result["result"]["structuredContent"]
    assert r["request_id"] and r["generation"] == c.generation
    for k in [
        "schema_version",
        "lab_id",
        "node_id",
        "operation",
        "collected_at",
        "duration_ms",
        "status",
        "data",
        "raw_evidence",
        "truncated",
        "error_code",
    ]:
        assert k in r


@then("the three named scenarios are reported as unavailable")
def catalogue(c):
    items = c.result["result"]["structuredContent"]["data"]["scenarios"]
    assert {x["id"] for x in items} == {
        "core-link-failure",
        "customer-bgp-failure",
        "data-path-degradation",
    }
    assert all(x["available"] is False for x in items)


@then('the native MCP result is an error with "{code}"')
def unavailable(c, code):
    r = c.result["result"]
    assert r["isError"] is True and r["structuredContent"]["error_code"] == code


@when("the topology snapshot is read twice")
def snapshot(c):
    c.first = c.topology.snapshot()
    c.second = c.topology.snapshot()


@then("it has eight expected nodes and exactly the nine brief links")
def brief(c):
    assert {n["id"] for n in c.first["nodes"]} == {
        "p1",
        "p2",
        "pe1",
        "pe2",
        "ce1",
        "ce2",
        "host1",
        "host2",
    }
    expected = {
        frozenset(x)
        for x in [
            ("p1", "p2"),
            ("p1", "pe1"),
            ("p2", "pe1"),
            ("p1", "pe2"),
            ("p2", "pe2"),
            ("pe1", "ce1"),
            ("pe2", "ce2"),
            ("ce1", "host1"),
            ("ce2", "host2"),
        ]
    }
    assert {frozenset([x["source"], x["target"]]) for x in c.first["links"]} == expected
    assert all(n["expected"] for n in c.first["nodes"])


@then("all routing and link states are unknown")
def unknown(c):
    assert all(n["state"] == "unknown" for n in c.first["nodes"] + c.first["links"])


@then("the snapshots have the same revision and collection time")
def stable(c):
    assert c.first == c.second


@then("returned snapshots cannot mutate the stored graph")
def immutable(c):
    c.first["nodes"].clear()
    assert len(c.topology.snapshot()["nodes"]) == 8


@given("observations contain a running p1 and an exited p2")
def presence(c):
    observations(c)


@then("runtime collection is {state}")
def runtime(c, state):
    assert c.first["runtime_status"] == state


@then("p1 is running with unknown routing state")
def running(c):
    n = next(n for n in c.first["nodes"] if n["id"] == "p1")
    assert n["container_state"] == "running" and n["state"] == "unknown"


@then("p2 is exited with unavailable node state")
def stopped(c):
    n = next(n for n in c.first["nodes"] if n["id"] == "p2")
    assert n["container_state"] == "exited" and n["state"] == "unavailable"


@then("all link states remain unknown")
def links_unknown(c):
    assert all(x["state"] == "unknown" for x in c.first["links"])


@given('observations are "{condition}"')
def bad_observation(c, condition):
    values = {
        "stale": {"collected_at": "2000-01-01T00:00:00Z"},
        "future": {"collected_at": "2999-01-01T00:00:00Z"},
        "another lab": {"lab_id": "wrong"},
        "another generation": {"generation": 2},
        "unknown node": {"nodes": {"alien": {}}},
        "invalid entry": {"nodes": {"p1": "wrong"}},
    }
    if condition in values:
        observations(c, **values[condition])
    else:
        c.topology.observations.write_text("{" if condition == "malformed" else "x" * 65537)


@given('the inventory has "{defect}"')
def bad_inventory(c, defect):
    t = copy.deepcopy(c.inventory)
    e = t["links"][0]["endpoints"][0]
    if defect == "duplicate node":
        t["nodes"][1]["id"] = t["nodes"][0]["id"]
    elif defect == "unknown endpoint":
        e["node"] = "alien"
    elif defect == "reused interface":
        t["links"][1]["endpoints"][1]["interface"] = e["interface"]
    elif defect == "overlapping subnet":
        t["links"][1]["subnet"] = t["links"][0]["subnet"]
    elif defect == "gateway collision":
        e["address"] = "10.200.1.1/29"
    elif defect == "invalid interface":
        e["interface"] = "../../etc"
    elif defect == "repeated endpoint":
        t["links"][0]["endpoints"][1]["node"] = e["node"]
    c.bad = t


@when("the Python topology model is constructed")
def build_model(c):
    path = c.root / "bad.json"
    path.write_text(json.dumps(c.bad))
    try:
        Topology(path, c.root / "observations.json")
    except ValueError:
        c.validation_failed = True
    else:
        c.validation_failed = False


@when('"{role}" requests "{method}" "{path}"')
def http_request(c, role, method, path):
    c.response = run(
        c.server.handle_http_request_async(
            method=method, path=path, headers=headers(role), body=b"", peer="127.0.0.1"
        )
    )


@then("the HTTP status is {status:d}")
def http_status(c, status):
    assert c.response.status == status, (c.response.status, c.response.body)


@then("the HTTP error code is stream_limit")
def stream_limit(c):
    assert json.loads(c.response.body)["error_code"] == "stream_limit"


@then("the HTML loads only the generated local application assets")
def assets(c):
    assert b"/assets/main.js" in c.response.body and b"/assets/styles.css" in c.response.body
    assert b"https://" not in c.response.body


@then("the response has no-sniff and restrictive script and frame policies")
def response_headers(c):
    h = dict(c.response.headers)
    assert h["X-Content-Type-Options"] == "nosniff"
    assert (
        "script-src 'self'" in h["Content-Security-Policy"]
        and "frame-ancestors 'none'" in h["Content-Security-Policy"]
    )


@given("a local authenticated HTTP service is running")
def wire(c):
    # Shared process harness only; scenarios make their own assertions, not run unittest methods.
    from test_transport import TransportTests

    c.wire = TransportTests
    c.wire.setUpClass()


def wire_rpc(c, role, method, params=None, extra=None):
    return c.wire.request(
        "POST",
        "/mcp",
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        role,
        extra,
    )


@when("an Operator and a God client initialize sessions")
def init(c):
    c.sessions = {}
    for role in ["operator", "god"]:
        status, h, body = wire_rpc(
            c,
            role,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "clientInfo": {"name": "bdd", "version": "1"},
                "capabilities": {},
            },
        )
        assert status == 200 and json.loads(body)["result"]["protocolVersion"] == "2025-03-26"
        c.sessions[role] = {"Mcp-Session-Id": h["Mcp-Session-Id"]}


@then("each client discovers only its permitted tools")
def wire_tools(c):
    for role, count in [("operator", 6), ("god", 10)]:
        status, _, body = wire_rpc(c, role, "tools/list", extra=c.sessions[role])
        assert status == 200
        assert len(json.loads(body)["result"]["tools"]) == count


@then("an Operator cannot reuse a God session")
def session_boundary(c):
    assert wire_rpc(c, "operator", "tools/list", extra=c.sessions["god"])[0] == 403


@then("deleting a session makes subsequent use fail")
def delete(c):
    for role, h in c.sessions.items():
        assert c.wire.request("DELETE", "/mcp", role=role, extra=h)[0] == 200
        assert wire_rpc(c, role, "tools/list", extra=h)[0] == 404


@when('a caller sends an unauthenticated "{method}" MCP request')
def wire_noauth(c, method):
    c.wire_status = c.wire.request(method, "/mcp")[0]


@then("the wire status is {status:d}")
def wire_status(c, status):
    assert c.wire_status == status


@when("a caller sends an unapproved Origin header")
def origin(c):
    c.wire_status = c.wire.request(
        "GET", "/api/v1/topology", role="operator", extra={"Origin": "https://unapproved.example"}
    )[0]


@when("an Operator sends an excessive log limit over HTTP")
def wire_query(c):
    c.wire_status = c.wire.request("GET", "/api/v1/nodes/p1/logs?limit=501", role="operator")[0]


@given("a topology stream is open")
def topo_stream(c):
    c.stream = c.server.events()
    assert b"topology.snapshot" in run(anext(c.stream))


@when("container observations change")
def topo_change(c):
    observations(c)


@then("the stream emits topology.changed with the new revision")
def topo_event(c):
    chunk = run(anext(c.stream))
    assert b"topology.changed" in chunk and c.topology.snapshot()["revision"].encode() in chunk


@then("closing it releases its slot")
def close(c):
    run(c.stream.aclose())
    c.stream = None
    assert c.server.streams == 0


@then("reconnecting starts with topology.snapshot rather than replay")
def reconnect(c):
    c.stream = c.server.events()
    assert b"topology.snapshot" in run(anext(c.stream))


@given("current node log entries and a log stream")
def log_stream(c):
    logs(c)
    c.stream = c.server.log_events("p1")
    assert b"logs.snapshot" in run(anext(c.stream))


@when("the node log snapshot changes")
def log_change(c):
    logs(c, entries=[])


@then("the stream emits logs.changed without message contents")
def log_event(c):
    chunk = run(anext(c.stream))
    assert b"logs.changed" in chunk and b"message" not in chunk


@given("sixteen active streams")
def cap(c):
    c.server.streams = 16


@when("auxiliary response headers conflict with transport framing")
def framing(c):
    c.invalid = [
        MCPHTTPResponse(200, headers=((name, "bad"),))
        for name in ["Content-Length", "Transfer-Encoding", "Connection", "Content-Type"]
    ]


@then("the response validator rejects them")
def reject_framing(c):
    assert all(validate_http_response(r, max_bytes=1024) is None for r in c.invalid)


@then("streamed bodies cannot also have a buffered body")
def exclusive(c):
    c.stream = c.server.events()
    assert (
        validate_http_response(MCPHTTPResponse(200, b"body", stream=c.stream), max_bytes=1024)
        is None
    )


@when("an Operator opens a node log SSE stream")
def wire_sse(c):
    c.conn = http.client.HTTPConnection("127.0.0.1", c.wire.port, timeout=5)
    c.conn.request("GET", "/api/v1/nodes/p1/logs/events", headers=headers("operator"))
    c.sse = c.conn.getresponse()


@then("logs.snapshot arrives before EOF without length or chunked framing")
def wire_sse_result(c):
    try:
        assert c.sse.status == 200
        assert (
            c.sse.getheader("Content-Length") is None
            and c.sse.getheader("Transfer-Encoding") is None
        )
        assert c.sse.readline() == b"event: logs.snapshot\n"
    finally:
        c.sse.close()
        c.conn.close()


@given("a successful empty node log snapshot")
def empty(c):
    logs(c, entries=[])


@given("five valid node log entries")
def five(c):
    logs(c)


@when("the node log page is requested")
def page(c):
    c.page = c.store.page("p1")


@then("its status is ok and there are no entries")
def empty_ok(c):
    assert c.page["status"] == "ok" and c.page["data"]["entries"] == []


@when("two pages of size two are requested")
def pages(c):
    c.page = c.store.page("p1", 2)
    c.next = c.store.page("p1", 2, c.page["data"]["next_cursor"])


@then("their entries are deterministic and do not overlap")
def distinct(c):
    assert c.page["data"] == c.store.page("p1", 2)["data"]
    assert len(c.next["data"]["entries"]) == 2
    assert not {e["id"] for e in c.page["data"]["entries"]} & {
        e["id"] for e in c.next["data"]["entries"]
    }


def expired(c, node):
    try:
        c.store.page(node, 2, c.page["data"]["next_cursor"])
    except ValueError as e:
        assert str(e) == "cursor_expired"
    else:
        raise AssertionError("cursor was accepted")


@then("a cursor cannot cross nodes")
def cross(c):
    expired(c, "p2")


@then("rotating the snapshot expires its previous cursor")
def rotate(c):
    logs(c, entries=[])
    expired(c, "p1")


@given('the log snapshot is "{condition}"')
def bad_logs(c, condition):
    if condition == "missing":
        return
    if condition == "symlink":
        target = c.root / "target"
        target.write_text("{}")
        c.logfile.symlink_to(target)
        return
    if condition in {"malformed", "oversized"}:
        c.logfile.write_text("{" if condition == "malformed" else "x" * 65537)
        return
    overrides = {
        "stopped node": {"status": "unavailable", "error_code": "node_unavailable"},
        "timed out": {"status": "unavailable", "error_code": "collection_timeout"},
        "command failure": {"status": "unavailable", "error_code": "collection_failed"},
        "output cap": {"status": "unavailable", "error_code": "output_limit"},
        "invalid entry": {"entries": [{}]},
        "wrong node": {"node_id": "p2"},
        "another lab": {"lab_id": "other"},
        "another generation": {"generation": 2},
        "stale": {
            "entries": [],
            "collected_at": (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat(),
        },
    }
    logs(c, **overrides[condition])


@then('the log error code is "{error}"')
def log_error(c, error):
    assert c.page["error_code"] == error, c.page


@given("valid entries containing configured credentials and secret patterns")
def secret_logs(c):
    p = logs(c)
    p["entries"][0]["message"] = (
        "token=hunter Bearer credential configured-credential https://u:pw@host <script>hello</script> \x1b[31m"
    )
    for index, message in [
        (4, "-----BEGIN PRIVATE KEY-----"),
        (3, "private material"),
        (2, "-----END PRIVATE KEY-----"),
    ]:
        p["entries"][index]["message"] = message
    c.logfile.write_text(json.dumps(p))


@then("recognized secrets and terminal escapes are absent")
def sanitized(c):
    text = json.dumps(c.page)
    for value in ["hunter", "configured-credential", "Bearer credential", "u:pw", "\\u001b"]:
        assert value not in text


@then("ordinary HTML is returned as inert message text")
def html(c):
    assert "<script>hello</script>" in json.dumps(c.page)


@then("private key blocks are absent")
def pem(c):
    assert "private material" not in json.dumps(c.page) and "PRIVATE KEY" not in json.dumps(c.page)


@given("a near-limit log snapshot")
def big(c):
    p = logs(c)
    p["entries"] = [
        p["entries"][0] | {"id": f"{i:024x}", "message": "<>&" * 500} for i in range(30)
    ]
    c.logfile.write_text(json.dumps(p))


@when("a page of 500 entries is requested")
def max_page(c):
    c.page = c.store.page("p1", 500)


@then("its encoded response is less than 64 KiB")
def bounded(c):
    assert len(json.dumps(c.page).encode()) < 65536


@then("any omitted entries have an older-page cursor")
def cursor_for_omitted(c):
    if len(c.page["data"]["entries"]) < c.page["data"]["retained_count"]:
        assert c.page["data"]["next_cursor"]


@given("generated node baseline files are available")
def generated_configuration(c):
    directory = c.root / "configs"
    for node in ["p1", "host1"]:
        (directory / node).mkdir(parents=True)
    (directory / "p1/frr.conf").write_text("hostname p1\nrouter bgp 65000\n")
    (directory / "p1/daemons").write_text("zebra=yes\nbgpd=yes\nospfd=yes\n")
    (directory / "host1/network.json").write_text('{"gateway":"10.200.8.3"}')
    c.server.config_root = directory


@then('the configuration tree lists only "{files}" beneath "{node}"')
def configuration_tree(c, files, node):
    assert c.response.status == 200, (c.response.status, c.response.body)
    data = json.loads(c.response.body)["data"]
    assert data["node_id"] == node
    assert sorted(x["name"] for x in data["files"]) == sorted(files.split(","))


@then("the configuration response is labelled declared baseline rather than running state")
def configuration_source(c):
    data = json.loads(c.response.body)["data"]
    assert data["source"] == "declared_baseline" and data["running_verified"] is False


@then('the configuration file contains "{text}" with a content revision')
def configuration_content(c, text):
    assert c.response.status == 200, (c.response.status, c.response.body)
    data = json.loads(c.response.body)["data"]
    assert text in data["content"] and len(data["revision"]) == 64


@given('the p1 baseline file is "{condition}"')
def configuration_bad(c, condition):
    p = c.server.config_root / "p1/frr.conf"
    if condition == "missing":
        p.unlink()
    elif condition == "symlink":
        p.unlink()
        p.symlink_to(c.tokens)
    elif condition == "oversized":
        p.write_text("x" * 32769)


@then('configuration access fails with "{error}"')
def configuration_failure(c, error):
    assert c.response.status in {413, 503}
    assert json.loads(c.response.body)["error_code"] == error


@given("the p1 baseline contains secret-bearing configuration directives")
def configuration_secrets(c):
    (c.server.config_root / "p1/frr.conf").write_text(
        "hostname p1\n neighbor 10.0.0.1 password never-show-this\n enable secret do-not-show\n token=opaque-secret\n"
    )


@then("the configuration secret values are absent and redaction is marked")
def configuration_sanitized(c):
    data = json.loads(c.response.body)["data"]
    for secret in ["never-show-this", "do-not-show", "opaque-secret"]:
        assert secret not in data["content"]
    assert data["redacted"] is True


@given("the p1 baseline contains a multiline private key")
def configuration_private_key(c):
    (c.server.config_root / "p1/frr.conf").write_text(
        "hostname p1\n-----BEGIN PRIVATE KEY-----\ncHJpdmF0ZS1rZXktYm9keS1zaG91bGQtbm90LWJlLXZpc2libGU=\n-----END PRIVATE KEY-----\n"
    )


@then("no private key body or delimiter is present in the configuration response")
def configuration_private_key_removed(c):
    assert c.response.status == 200
    content = json.loads(c.response.body)["data"]["content"]
    assert "cHJpdmF0ZS1rZXktYm9keS1zaG91bGQtbm90LWJlLXZpc2libGU=" not in content
    assert "-----BEGIN" not in content and "-----END" not in content


@then("get_evidence exposes only topology, logs and declared configuration selectors")
def evidence_discovery(c):
    tool = next((t for t in c.result["result"]["tools"] if t["name"] == "get_evidence"), None)
    assert tool is not None
    assert tool["inputSchema"]["properties"]["kind"]["enum"] == [
        "topology",
        "logs",
        "configuration",
    ]
    assert tool["inputSchema"]["additionalProperties"] is False


@when('an Operator requests "{kind}" evidence over MCP and HTTP')
def evidence_parity(c, kind):
    args = {"kind": kind}
    path = "/api/v1/topology"
    if kind == "logs":
        args.update(node_id="p1", limit=10)
        path = "/api/v1/nodes/p1/logs?limit=10"
    elif kind == "configuration":
        args.update(node_id="p1", file="frr.conf")
        path = "/api/v1/nodes/p1/config/frr.conf"
    c.mcp_evidence = rpc(c, "operator", "tools/call", {"name": "get_evidence", "arguments": args})
    http_request(c, "operator", "GET", path)


@then("both surfaces return the same permitted data and failure state")
def evidence_matches(c):
    assert "result" in c.mcp_evidence, c.mcp_evidence
    tool = c.mcp_evidence["result"]["structuredContent"]
    web = json.loads(c.response.body)
    if tool["operation"] == "get_topology":
        assert tool["data"] == web
    else:
        assert tool["data"] == web["data"] and tool["error_code"] == web["error_code"]


@given("a controller state fixture containing an injected fault and a secret field")
def fixture_ground_truth(c):
    class Controller:
        def get_state(self):
            return {
                "state": "active",
                "scenario_id": "core-link-failure",
                "node_id": "p1",
                "interface": "to-p2",
                "generation": 1,
                "secret": "never-project-this",
                "parameters": {},
                "verified": True,
            }

    c.server.controller = Controller()


@then('"{visibility}" controller visibility is returned')
def projected_ground_truth(c, visibility):
    data = json.loads(c.response.body)
    if visibility == "bounded":
        assert data["controller"]["scenario_id"] == "core-link-failure" and data["view"] == "god"
    else:
        assert "controller" not in data
    assert "never-project-this" not in c.response.body.decode()


@then("the controller projection reports unavailable rather than baseline")
def controller_absent(c):
    assert c.response.status == 200
    data = json.loads(c.response.body)["controller"]
    assert data["state"] == "unavailable" and data["error_code"] == "backend_not_configured"


@when("valid God Basic credentials are supplied")
def god_basic(c):
    c.god_headers = {
        "authorization": "Basic " + base64.b64encode(("god:" + "g" * 40).encode()).decode()
    }
    c.god_principal = c.policy.authenticate(c.god_headers)


@then("the principal has God capability and the capability response exposes no credential")
def browser_capability(c):
    assert c.god_principal and c.god_principal.roles == ("god",)
    response = run(
        c.server.handle_http_request_async(
            method="GET", path="/api/v1/view", headers=c.god_headers, body=b"", peer="127.0.0.1"
        )
    )
    assert response.status == 200 and json.loads(response.body)["can_god"] is True
    assert "g" * 40 not in response.body.decode()


@then("incorrect God Basic credentials are denied")
def bad_god_basic(c):
    assert (
        c.policy.authenticate({"authorization": "Basic " + base64.b64encode(b"god:bad").decode()})
        is None
    )


@when("Operator and God request full-view topology streams")
def visibility_streams(c):
    async def check():
        c.op_stream = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/events?view=god",
            headers=headers("operator"),
            body=b"",
            peer="127.0.0.1",
        )
        r = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/events?view=god",
            headers=headers("god"),
            body=b"",
            peer="127.0.0.1",
        )
        assert r.status == 200
        c.event = await anext(r.stream)
        await r.stream.aclose()

    run(check())


@then("Operator is denied and God receives metadata-only invalidation")
def visibility_stream_result(c):
    assert (
        c.op_stream.status == 403
        and b"topology.snapshot" in c.event
        and b"scenario_id" not in c.event
        and b"never-project" not in c.event
    )


@then("opening the God stream does not change subsequent Operator snapshots")
def no_global_projection(c):
    http_request(c, "operator", "GET", "/api/v1/topology")
    assert "controller" not in json.loads(c.response.body)


@when("an Operator supplies undocumented evidence fields or unsafe filenames")
def unsafe_evidence(c):
    c.evidence_denied = [
        rpc(c, "operator", "tools/call", {"name": "get_evidence", "arguments": args})
        for args in [
            {"kind": "configuration", "node_id": "p1", "file": "../../secrets"},
            {"kind": "logs", "node_id": "p1", "command": "id"},
            {"kind": "controller"},
            {"kind": "topology", "node_id": "p1"},
        ]
    ]


@then("each call is rejected without exposing host or controller state")
def rejected_evidence(c):
    assert all("error" in r and r["error"]["code"] == -32602 for r in c.evidence_denied), (
        c.evidence_denied
    )
