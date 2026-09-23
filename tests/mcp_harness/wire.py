"""Independent HTTP client: no uMCP imports or in-process RPC dispatch."""

import concurrent.futures
import http.client
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPERATOR = {"list_nodes", "get_interfaces", "get_routes", "get_neighbors", "ping"}
GOD = {"list_fault_scenarios", "get_fault_state", "apply_fault", "reset_lab"}
ARGS = {
    "get_interfaces": {"node_id": "p1"},
    "get_routes": {"node_id": "p1"},
    "get_neighbors": {"node_id": "p1", "protocol": "bgp"},
    "ping": {"node_id": "p1", "destination": "10.200.1.3", "count": 1},
    "apply_fault": {"scenario_id": "core-link-failure", "idempotency_key": "harness-request"},
    "reset_lab": {"idempotency_key": "harness-request"},
}


class Wire:
    def __init__(self, ttl=1800):
        self.tmp = tempfile.TemporaryDirectory(prefix="minicore-mcp-")
        self.path = Path(self.tmp.name)
        self.tokens = {role: secrets.token_hex(24) for role in ["operator", "god"]}
        self.ttl = ttl
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.streams = []
        self.proc = None
        self.log = None
        self.start()

    def start(self):
        (self.path / "tokens.json").write_text(json.dumps(self.tokens))
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.log = open(self.path / "service.log", "a")
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tests/mcp_harness/fixture.py")],
            env=os.environ
            | {
                "TEST_ROOT": str(ROOT),
                "TEST_TMP": str(self.path),
                "TEST_PORT": str(self.port),
                "TEST_TTL": str(self.ttl),
            },
            stdout=self.log,
            stderr=self.log,
        )
        for _ in range(100):
            if self.proc.poll() is not None:
                raise RuntimeError((self.path / "service.log").read_text())
            try:
                if self.request("GET", "/healthz")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.02)
        raise RuntimeError("Fixture startup timeout")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        if self.log:
            self.log.close()

    def close(self):
        for response, conn in self.streams:
            response.close()
            conn.close()
        self.stop()
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.tmp.cleanup()

    def request(
        self,
        method,
        path="/mcp",
        payload=None,
        role="operator",
        session=None,
        version="2025-03-26",
        extra=None,
    ):
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if role:
            headers["Authorization"] = "Bearer " + self.tokens[role]
        if version:
            headers["MCP-Protocol-Version"] = version
        if session:
            headers["Mcp-Session-Id"] = session
        headers.update(extra or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        raw = (
            payload
            if isinstance(payload, (bytes, str))
            else json.dumps(payload)
            if payload is not None
            else None
        )
        conn.request(method, path, raw, headers)
        r = conn.getresponse()
        body = r.read()
        status = r.status
        h = dict(r.getheaders())
        conn.close()
        try:
            data = json.loads(body) if body else None
        except ValueError:
            data = body.decode(errors="replace")
        return status, h, data

    def rpc(self, method, params=None, role="operator", session=None, request_id=1, **kw):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if request_id is not None:
            payload["id"] = request_id
        return self.request("POST", payload=payload, role=role, session=session, **kw)

    def initialize(self, role="operator", version="2025-03-26"):
        status, h, data = self.rpc(
            "initialize",
            {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "independent-wire", "version": "1"},
            },
            role=role,
            version=None,
        )
        assert status == 200 and "result" in data, (status, data)
        return h["Mcp-Session-Id"], data["result"]["protocolVersion"]

    def call(self, name, role="operator", session=None, request_id=10, meta=None):
        params = {"name": name, "arguments": ARGS.get(name, {})}
        if meta:
            params["_meta"] = meta
        return self.rpc("tools/call", params, role, session, request_id)

    def slow(self, role="operator", session=None, request_id=10, meta=None):
        future = self.pool.submit(self.call, "get_routes", role, session, request_id, meta)
        time.sleep(0.12)
        return future

    def stream(self, session, role="operator"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request(
            "GET",
            "/mcp",
            headers={
                "Authorization": "Bearer " + self.tokens[role],
                "Mcp-Session-Id": session,
                "MCP-Protocol-Version": "2025-03-26",
                "Accept": "text/event-stream",
            },
        )
        response = conn.getresponse()
        self.streams.append((response, conn))
        return response, conn

    def raw(self, headers, body=b""):
        data = (
            f"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n" + headers + "\r\n"
        ).encode() + body
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as s:
            s.sendall(data)
            result = s.recv(8192)
        return int(result.split(b" ")[1])
