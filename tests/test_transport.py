"""Authenticated wire tests against the same vendored uMCP listener used in Compose."""

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        secret = Path(cls.temp.name) / "tokens.json"
        secret.write_text(json.dumps({"operator": "o" * 40, "god": "g" * 40}))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.log = open(Path(cls.temp.name) / "service.log", "w")
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "minicore_mcp"],
            env=os.environ
            | {
                "MINICORE_ROOT": str(ROOT),
                "MINICORE_HOST": "127.0.0.1",
                "MINICORE_PORT": str(cls.port),
                "MINICORE_EXPOSURE_PROFILE": "authenticated",
                "MINICORE_TOKEN_FILE": str(secret),
            },
            stdout=cls.log,
            stderr=cls.log,
        )
        for _ in range(100):
            try:
                if cls.request("GET", "/healthz")[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(0.02)
        cls.proc.terminate()
        raise RuntimeError("Management service did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        cls.log.close()
        cls.temp.cleanup()

    @classmethod
    def request(cls, method, path, payload=None, role=None, extra=None):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=5)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if role:
            headers["Authorization"] = "Bearer " + role[0] * 40
        headers.update(extra or {})
        conn.request(method, path, json.dumps(payload) if payload else None, headers)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def rpc(self, method, role, params=None, headers=None):
        return self.request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            role,
            headers,
        )

    def test_roles_sessions_and_mutation_denials(self):
        for role, count in [("operator", 5), ("god", 9)]:
            status, h, body = self.rpc("initialize", role, {"protocolVersion": "2025-03-26"})
            self.assertEqual(status, 200)
            session = {"Mcp-Session-Id": h["Mcp-Session-Id"]}
            status, _, body = self.rpc("tools/list", role, headers=session)
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(body)["result"]["tools"]), count)
            status, _, body = self.rpc(
                "tools/call",
                role,
                {
                    "name": "apply_fault",
                    "arguments": {
                        "scenario_id": "core-link-failure",
                        "idempotency_key": "wire_test_123",
                    },
                },
                session,
            )
            self.assertEqual(status, 403 if role == "operator" else 200)
            if role == "god":
                self.assertTrue(json.loads(body)["result"]["isError"])
                self.assertEqual(self.rpc("tools/list", "operator", headers=session)[0], 403)
            self.assertEqual(self.request("DELETE", "/mcp", role=role, extra=session)[0], 200)
            self.assertEqual(self.rpc("tools/list", role, headers=session)[0], 404)

    def test_all_methods_require_authentication(self):
        for method in ["POST", "GET", "DELETE"]:
            self.assertEqual(self.request(method, "/mcp")[0], 401)
        for path in ["/", "/api/v1/topology", "/api/v1/events", "/api/v1/nodes/p1/logs"]:
            self.assertEqual(self.request("GET", path)[0], 401)

    def test_no_role_override_or_operator_ground_truth(self):
        status, _, body = self.rpc("tools/list", "operator", headers={"X-Role": "god"})
        self.assertEqual(status, 200)
        self.assertNotIn(b"apply_fault", body)
        status, _, body = self.request("GET", "/api/v1/topology", role="operator")
        self.assertEqual(status, 200)
        for value in [b"idempotency", b"scenario_id", b"fault_state", b"gggggggg"]:
            self.assertNotIn(value, body)

    def test_real_auxiliary_stream_has_single_framing(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/v1/events", headers={"Authorization": "Bearer " + "o" * 40})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertIsNone(response.getheader("Content-Length"))
        self.assertIsNone(response.getheader("Transfer-Encoding"))
        self.assertEqual(response.getheader("Connection"), "close")
        self.assertTrue(response.readline().startswith(b"id:"))
        self.assertEqual(response.readline(), b"event: topology.snapshot\n")
        response.close()
        conn.close()
