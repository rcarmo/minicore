"""Host-to-Compose HTTP/MCP smoke; uses real published port, not in-process calls."""

import http.client
import json
import os
from urllib.parse import urlsplit

u = urlsplit(os.environ.get("MINICORE_URL", "http://127.0.0.1:19000"))


def request(method, path, body=None, headers=None):
    c = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"} | (
        headers or {}
    )
    c.request(method, path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse()
    status = r.status
    hs = dict(r.getheaders())
    data = r.read()
    c.close()
    return status, hs, json.loads(data) if data else None


assert request("GET", "/healthz")[0] == 200
s = request("GET", "/api/v1/topology")[2]
assert len(s["nodes"]) == 8 and len(s["links"]) == 9
status, h, p = request(
    "POST",
    "/mcp",
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "minicore-smoke", "version": "0.1"},
        },
    },
)
assert status == 200 and p["result"]["protocolVersion"] == "2025-03-26"
h = {"Mcp-Session-Id": h["Mcp-Session-Id"], "MCP-Protocol-Version": "2025-03-26"}
assert (
    request("POST", "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, h)[0] == 202
)
r = request("POST", "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, h)[2]
assert {t["name"] for t in r["result"]["tools"]} == {
    "list_nodes",
    "get_interfaces",
    "get_routes",
    "get_neighbors",
    "ping",
}
for name, args in [
    ("list_nodes", {}),
    ("get_interfaces", {"node_id": "p1"}),
    ("get_routes", {"node_id": "p1"}),
    ("get_neighbors", {"node_id": "p1", "protocol": "bgp"}),
    ("ping", {"node_id": "p1", "destination": "10.200.1.3"}),
]:
    status, _, r = request(
        "POST",
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
        h,
    )
    assert status == 200
    if name != "get_routes":
        assert r["result"]["isError"] == (name != "list_nodes")
    else:
        evidence = r["result"]["structuredContent"]
        assert (not r["result"]["isError"] and isinstance(evidence["data"], dict)) or evidence[
            "error_code"
        ] == "backend_not_configured"
    assert json.loads(r["result"]["content"][0]["text"]) == r["result"]["structuredContent"]
assert (
    request(
        "POST",
        "/mcp",
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "reset_lab"}},
        h,
    )[0]
    == 403
)
# Real streaming response must emit before EOF and carry no conflicting framing headers.
c = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
c.request("GET", "/api/v1/events")
r = c.getresponse()
assert r.status == 200 and r.getheader("Content-Type") == "text/event-stream"
assert r.getheader("Transfer-Encoding") is None and r.getheader("Content-Length") is None
assert r.readline().startswith(b"id:")
assert r.readline() == b"event: topology.snapshot\n"
r.close()
c.close()
# MCP session stream GET is independent from topology SSE.
c = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
c.request("GET", "/mcp", headers=h | {"Accept": "text/event-stream"})
r = c.getresponse()
assert r.status == 200
assert request("DELETE", "/mcp", headers=h)[0] == 200
r.close()
c.close()
assert request("GET", "/mcp", headers=h | {"Accept": "text/event-stream"})[0] == 404
log_status, _, log_page = request("GET", "/api/v1/nodes/p1/logs")
assert log_status in {200, 503}
assert log_page["node_id"] == "p1" and len(log_page["data"]["entries"]) <= 100
assert (log_status == 200) == (log_page["error_code"] is None)
assert request("GET", "/assets/../../secrets/mcp-tokens.json")[0] == 404
assert (
    request("GET", "/api/v1/topology", headers={"Origin": "https://unapproved.example"})[0] == 403
)
print(
    "PASS: host-to-Compose health, eight-node/nine-link topology, MCP lifecycle/five tools/denial, text-structured parity, topology SSE, origin/path checks"
)
