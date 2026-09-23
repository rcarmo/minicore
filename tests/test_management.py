import base64
import json
import tempfile
import unittest
from pathlib import Path

from minicore_mcp.model import Topology, utc_now
from minicore_mcp.policy import GOD, OPERATOR, Policy
from minicore_mcp.server import Server
from umcp_shared import MCPHTTPResponse, MCPRequestContext, validate_http_response

ROOT = Path(__file__).resolve().parents[1]


class ManagementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.tokens = self.path / "tokens.json"
        self.tokens.write_text(json.dumps({"operator": "o" * 40, "god": "g" * 40}))
        self.policy = Policy("authenticated", self.tokens)
        self.topology = Topology(ROOT / "inventory/topology.json", self.path / "observations.json")
        self.server = Server(self.topology, self.policy, ROOT / "web-ui/dist")

    def context(self, mode):
        return MCPRequestContext(
            transport="streamable-http",
            principal=mode,
            headers={"authorization": "Bearer " + mode[0] * 40},
        )

    async def rpc(self, mode, method, params=None):
        return await self.server.process_request_async(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}),
            context=self.context(mode),
        )

    async def test_topology_has_complete_brief(self):
        t = self.topology.snapshot()
        self.assertEqual(
            {n["id"] for n in t["nodes"]},
            {"p1", "p2", "pe1", "pe2", "ce1", "ce2", "host1", "host2"},
        )
        self.assertEqual(len(t["links"]), 9)
        self.assertTrue(all(n["state"] == "unknown" for n in t["nodes"]))
        self.assertEqual(t, self.topology.snapshot())

    async def test_role_filtered_discovery(self):
        for mode, expected in [("operator", OPERATOR), ("god", OPERATOR | GOD)]:
            result = await self.rpc(mode, "tools/list")
            self.assertEqual({t["name"] for t in result["result"]["tools"]}, expected)

    async def test_operator_cannot_call_god(self):
        for name in GOD:
            result = await self.rpc("operator", "tools/call", {"name": name})
            self.assertEqual(result["error"]["message"], "authorization_denied")

    async def test_native_error_flag_and_fallback(self):
        r = (
            await self.rpc(
                "operator", "tools/call", {"name": "get_routes", "arguments": {"node_id": "p1"}}
            )
        )["result"]
        self.assertTrue(r["isError"])
        self.assertEqual(r["structuredContent"], json.loads(r["content"][0]["text"]))
        self.assertEqual(r["structuredContent"]["error_code"], "backend_not_configured")
        self.assertIsNone(r["structuredContent"]["data"])

    async def test_inventory_success(self):
        r = (await self.rpc("operator", "tools/call", {"name": "list_nodes"}))["result"]
        self.assertFalse(r["isError"])
        self.assertEqual(len(r["structuredContent"]["data"]["nodes"]), 8)

    async def test_invalid_inputs(self):
        cases = [
            ("ping", {"node_id": "p1", "destination": "8.8.8.8"}),
            ("ping", {"node_id": "p1", "destination": "10.200.1.2", "count": True}),
            ("ping", {"node_id": "p1", "destination": "10.200.1.2", "count": 6}),
            ("get_routes", {"node_id": "p1; ls"}),
            ("get_routes", {"node_id": "p1", "command": "id"}),
            ("get_routes", {"node_id": "p1", "prefix": "::/0"}),
            ("get_neighbors", {"node_id": "p1", "protocol": "rip"}),
            ("get_interfaces", {"node_id": "p1", "interface": "../../etc/passwd"}),
        ]
        for name, args in cases:
            r = await self.rpc("operator", "tools/call", {"name": name, "arguments": args})
            self.assertEqual(r["error"]["code"], -32602)

    async def test_god_returns_not_configured_without_side_effect(self):
        r = await self.rpc(
            "god",
            "tools/call",
            {
                "name": "apply_fault",
                "arguments": {
                    "scenario_id": "core-link-failure",
                    "idempotency_key": "test_key_123",
                },
            },
        )
        self.assertTrue(r["result"]["isError"])
        self.assertEqual(self.topology.snapshot()["generation"], 1)

    async def test_observations_never_imply_link_health(self):
        self.topology.observations.write_text(
            json.dumps(
                {
                    "lab_id": "minicore-local",
                    "generation": 1,
                    "collected_at": utc_now(),
                    "nodes": {
                        "p1": {"container_state": "running"},
                        "p2": {"container_state": "exited"},
                    },
                }
            )
        )
        t = self.topology.snapshot()
        self.assertEqual(t["nodes"][0]["state"], "unknown")
        self.assertEqual(t["nodes"][1]["state"], "unavailable")
        self.assertTrue(all(link["state"] == "unknown" for link in t["links"]))

    async def test_stale_or_malformed_observations(self):
        for contents in [
            "{",
            json.dumps(
                {
                    "lab_id": "minicore-local",
                    "generation": 1,
                    "collected_at": "2000-01-01T00:00:00Z",
                    "nodes": {},
                }
            ),
        ]:
            self.topology.observations.write_text(contents)
            self.assertEqual(self.topology.snapshot()["runtime_status"], "unavailable")

    async def test_policy_fail_closed(self):
        for h in [{}, {"authorization": "Bearer bad"}, {"authorization": "Basic !!!"}]:
            self.assertIsNone(self.policy.authenticate(h))
        self.assertEqual(Policy("private", self.tokens).authenticate({}).roles, ("operator",))
        self.tokens.write_text('{"god":"tiny"}')
        with self.assertRaises(ValueError):
            Policy("private", self.tokens)
        self.tokens.unlink()
        with self.assertRaises(ValueError):
            Policy("authenticated", self.tokens)

    async def test_basic_is_operator_only(self):
        for role, char in [("operator", "o"), ("god", "g")]:
            p = self.policy.authenticate(
                {
                    "authorization": "Basic "
                    + base64.b64encode(f"{role}:{char * 40}".encode()).decode()
                }
            )
            self.assertEqual(p.name if p else None, "operator" if role == "operator" else None)

    async def test_http_boundaries(self):
        async def get(path, auth=True, method="GET"):
            return await self.server.handle_http_request_async(
                method=method,
                path=path,
                headers=self.context("operator").headers if auth else {},
                body=b"",
                peer="127.0.0.1",
            )

        self.assertEqual((await get("/api/v1/topology", False)).status, 401)
        self.assertEqual((await get("/healthz", False)).status, 200)
        self.assertEqual((await get("/assets/../../secrets/mcp-tokens.json")).status, 404)
        self.assertEqual((await get("/api/v1/apply_fault", method="POST")).status, 405)
        self.assertEqual((await get("/api/v1/nodes/p1/logs")).status, 503)
        self.assertEqual((await get("/api/v1/nodes/nonsense")).status, 404)

    async def test_stream_cleanup_and_limit(self):
        generator = self.server.events()
        first = await anext(generator)
        self.assertIn(b"topology.snapshot", first)
        self.assertEqual(self.server.streams, 1)
        await generator.aclose()
        self.assertEqual(self.server.streams, 0)

    async def test_vendor_response_validation(self):
        self.assertIsNone(
            validate_http_response(
                MCPHTTPResponse(200, headers=(("Transfer-Encoding", "chunked"),)), max_bytes=1024
            )
        )
        self.assertIsNone(
            validate_http_response(
                MCPHTTPResponse(200, headers=(("X-Test", "x\r\ny"),)), max_bytes=1024
            )
        )
        g = self.server.events()
        self.assertIsNotNone(validate_http_response(MCPHTTPResponse(200, stream=g), max_bytes=1024))
        self.assertIsNone(
            validate_http_response(MCPHTTPResponse(200, b"body", stream=g), max_bytes=1024)
        )
        await g.aclose()


if __name__ == "__main__":
    unittest.main()
