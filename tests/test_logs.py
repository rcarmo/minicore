import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from minicore_mcp.logs import LogStore, redact
from minicore_mcp.model import Topology, utc_now
from minicore_mcp.policy import Policy
from minicore_mcp.server import Server

ROOT = Path(__file__).resolve().parents[1]


class LogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.topology = Topology(ROOT / "inventory/topology.json", self.root / "observations.json")
        self.store = LogStore(self.topology, ["configured-credential"])
        self.store.root.mkdir()
        self.path = self.store.root / "p1.json"
        self.server = Server(
            self.topology, Policy("private", self.root / "tokens.json"), ROOT / "web-ui/dist"
        )

    def save(self, **changes):
        stamp = utc_now()
        payload = {
            "schema_version": "1.0",
            "lab_id": "minicore-local",
            "generation": 1,
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
        self.path.write_text(json.dumps(payload))
        return payload

    async def get(self, path, headers=None):
        return await self.server.handle_http_request_async(
            method="GET", path=path, headers=headers or {}, body=b"", peer="127.0.0.1"
        )

    async def test_missing_empty_and_success_are_distinct(self):
        self.assertEqual(self.store.page("p1")["error_code"], "backend_not_configured")
        self.save(entries=[])
        page = self.store.page("p1")
        self.assertEqual(page["status"], "ok")
        self.assertEqual(page["data"]["entries"], [])
        self.save()
        self.assertEqual(len(self.store.page("p1")["data"]["entries"]), 5)

    async def test_pages_cursor_rotation_and_node_binding(self):
        self.save()
        first = self.store.page("p1", 2)
        second = self.store.page("p1", 2, first["data"]["next_cursor"])
        self.assertFalse(
            {e["id"] for e in first["data"]["entries"]}
            & {e["id"] for e in second["data"]["entries"]}
        )
        with self.assertRaisesRegex(ValueError, "cursor_expired"):
            self.store.page("p2", 2, first["data"]["next_cursor"])
        self.save(entries=[])
        with self.assertRaisesRegex(ValueError, "cursor_expired"):
            self.store.page("p1", 2, first["data"]["next_cursor"])

    async def test_bad_snapshots_fail_closed(self):
        for content in ["{", "[]", "x" * 65537]:
            self.path.write_text(content)
            self.assertEqual(self.store.page("p1")["error_code"], "invalid_log_snapshot")
        for changes in [{"source": "audit"}, {"entries": [{"message": "x"}]}, {"node_id": "p2"}]:
            self.save(**changes)
            self.assertEqual(self.store.page("p1")["error_code"], "invalid_log_snapshot")
        self.save(generation=2)
        self.assertEqual(self.store.page("p1")["error_code"], "generation_mismatch")
        self.assertEqual(self.store.page("p1")["data"]["entries"], [])

    async def test_unavailable_and_stale_retain_labelled_evidence(self):
        self.save(status="unavailable", error_code="node_unavailable")
        self.assertEqual(self.store.page("p1")["status"], "unavailable")
        self.assertEqual(len(self.store.page("p1")["data"]["entries"]), 5)
        now = datetime.now(timezone.utc)
        self.save(
            entries=[],
            collected_at=(now - timedelta(seconds=20)).isoformat(),
            window_start=(now - timedelta(minutes=15)).isoformat(),
        )
        self.assertEqual(self.store.page("p1")["error_code"], "collector_stale")

    async def test_defensive_redaction_and_text(self):
        p = self.save()
        message = "password=hunter Bearer abcde configured-credential https://user:pass@example.test <script>hi</script> \x1b[31m"
        p["entries"][0]["message"] = message
        self.path.write_text(json.dumps(p))
        text = json.dumps(self.store.page("p1"))
        for secret in ["hunter", "abcde", "configured-credential", "user:pass", "\\u001b"]:
            self.assertNotIn(secret, text)
        self.assertIn("<script>hi</script>", text)
        self.assertIn("[REDACTED]", redact("token: foo"))

    async def test_response_byte_bound(self):
        p = self.save()
        p["entries"] = [
            p["entries"][0] | {"id": f"{i:024x}", "message": "<>&" * 500} for i in range(30)
        ]
        self.path.write_text(json.dumps(p))
        self.assertLess(len(json.dumps(self.store.page("p1", 500)).encode()), 65536)

    async def test_query_validation_and_auth_on_both_routes(self):
        for suffix in [
            "?limit=0",
            "?limit=501",
            "?limit=-1",
            "?source=controller",
            "?limit=2&limit=3",
            "?cursor=bad",
            "?command=id",
            "?path=/etc/shadow",
            "/events?limit=1",
        ]:
            r = await self.get("/api/v1/nodes/p1/logs" + suffix)
            self.assertEqual(r.status, 400, suffix)
        self.assertEqual((await self.get("/api/v1/nodes/alien/logs")).status, 404)
        token = self.root / "tokens.json"
        token.write_text(json.dumps({"operator": "o" * 40}))
        self.server.policy = Policy("authenticated", token)
        for suffix in ["", "/events"]:
            self.assertEqual((await self.get("/api/v1/nodes/p1/logs" + suffix)).status, 401)

    async def test_stream_invalidates_without_log_payload_and_cleans_up(self):
        self.save()
        stream = self.server.log_events("p1")
        first = await anext(stream)
        self.assertIn(b"logs.snapshot", first)
        self.assertNotIn(b"message", first)
        self.assertEqual(self.server.streams, 1)
        self.save(entries=[])
        second = await anext(stream)
        self.assertIn(b"logs.changed", second)
        await stream.aclose()
        self.assertEqual(self.server.streams, 0)

    async def test_real_page_routes(self):
        self.save()
        first = await self.get("/api/v1/nodes/p1/logs?limit=2")
        self.assertEqual(first.status, 200)
        self.assertEqual(len(json.loads(first.body)["data"]["entries"]), 2)
        self.assertEqual((await self.get("/api/v1/nodes/p1logs")).status, 404)

    async def test_symlink_source_rejected(self):
        target = self.root / "target.json"
        target.write_text("{}")
        self.path.symlink_to(target)
        self.assertEqual(self.store.page("p1")["error_code"], "invalid_log_snapshot")
