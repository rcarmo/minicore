"""Bounded read-only pages over atomic host-collected node logs. No Docker access."""

import base64
import hashlib
import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone

MAX_BYTES = 64 * 1024
CODES = {"node_unavailable", "collection_failed", "collection_timeout", "output_limit"}


def redact(message: str, secrets=()) -> str:
    value = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", message)
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]", value, flags=re.I)
    value = re.sub(
        r"""((?:password|passwd|token|secret|api[_-]?key|authorization)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)""",
        r"\1[REDACTED]",
        value,
        flags=re.I,
    )
    return re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value, flags=re.I)


class LogStore:
    def __init__(self, topology, secrets=()):
        self.topology = topology
        self.root = topology.observations.parent / "node-logs"
        self.secrets: Iterable[str] = tuple(secrets)

    def page(self, node: str, limit=100, cursor=None):
        if node not in self.topology.nodes:
            raise ValueError("unknown_node")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("invalid_limit")
        error = None
        collected = None
        window = None
        truncated = False
        entries = []
        revision = "unavailable"
        path = self.root / f"{node}.json"
        try:
            if self.root.is_symlink() or path.is_symlink():
                raise ValueError("invalid path")
            with path.open("rb") as f:
                raw = f.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("oversized")
            snapshot = json.loads(raw)
            if (
                snapshot["lab_id"] != self.topology.inventory["lab_id"]
                or snapshot["generation"] != self.topology.inventory["generation"]
            ):
                error = "generation_mismatch"
            else:
                if (
                    snapshot["schema_version"] != "1.0"
                    or snapshot["node_id"] != node
                    or snapshot["source"] != "container"
                ):
                    raise ValueError("identity")
                collected = snapshot["collected_at"]
                stamp = datetime.fromisoformat(collected.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - stamp).total_seconds()
                window = snapshot["window_start"]
                window_time = datetime.fromisoformat(window.replace("Z", "+00:00"))
                if window_time > stamp or (stamp - window_time).total_seconds() > 901:
                    raise ValueError("window")
                error = snapshot["error_code"]
                if error not in CODES | {None} or snapshot["status"] != (
                    "unavailable" if error else "ok"
                ):
                    raise ValueError("status")
                if not -5 <= age <= 15:
                    error = "collector_stale"
                source_entries = snapshot["entries"]
                if not isinstance(source_entries, list) or len(source_entries) > 500:
                    raise ValueError("entry count")
                seen = set()
                private_key = False
                # Reapply redaction in chronological order for defensive PEM block handling.
                cleaned = []
                for entry in reversed(source_entries):
                    if set(entry) != {
                        "id",
                        "timestamp",
                        "source",
                        "severity",
                        "message",
                        "truncated",
                    }:
                        raise ValueError("fields")
                    if (
                        not isinstance(entry["id"], str)
                        or not re.fullmatch("[a-f0-9]{24}", entry["id"])
                        or entry["id"] in seen
                    ):
                        raise ValueError("ID")
                    seen.add(entry["id"])
                    if (
                        entry["source"] != "container"
                        or entry["severity"] not in {"error", "warning", "info", "unknown"}
                        or type(entry["truncated"]) is not bool
                    ):
                        raise ValueError("source/severity")
                    event_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if event_time < window_time or (event_time - stamp).total_seconds() > 5:
                        raise ValueError("event time")
                    message = entry["message"]
                    if not isinstance(message, str) or len(message.encode()) > 2052:
                        raise ValueError("message")
                    if re.search(r"-----BEGIN .*PRIVATE KEY-----", message):
                        private_key = True
                        continue
                    if re.search(r"-----END .*PRIVATE KEY-----", message):
                        private_key = False
                        continue
                    if private_key or re.fullmatch(r"[A-Za-z0-9+/=]{40,}", message.strip()):
                        continue
                    cleaned.append(entry | {"message": redact(message, self.secrets)})
                entries = sorted(cleaned, key=lambda e: (e["timestamp"], e["id"]), reverse=True)
                truncated = bool(snapshot["truncated"])
                revision = hashlib.sha256(
                    json.dumps(
                        [snapshot["generation"], entries, truncated], sort_keys=True
                    ).encode()
                ).hexdigest()[:24]
        except FileNotFoundError:
            error = "backend_not_configured"
        except (ValueError, KeyError, TypeError, OSError, AttributeError):
            error = "invalid_log_snapshot"
            entries = []
            collected = None
            window = None
        offset = 0
        if cursor:
            if not isinstance(cursor, str) or len(cursor) > 256:
                raise ValueError("invalid_cursor")
            try:
                c = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                if (
                    not isinstance(c, list)
                    or len(c) != 4
                    or type(c[3]) is not int
                    or not 0 <= c[3] <= 500
                ):
                    raise ValueError()
            except (ValueError, UnicodeError, TypeError):
                raise ValueError("invalid_cursor") from None
            if c[:3] != [node, self.topology.inventory["generation"], revision]:
                raise ValueError("cursor_expired")
            offset = c[3]
        page: list[dict] = []
        for entry in entries[offset : offset + limit]:
            if len(json.dumps(page + [entry]).encode()) > MAX_BYTES - 2048:
                truncated = True
                break
            page.append(entry)
        end = offset + len(page)
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps([node, self.topology.inventory["generation"], revision, end]).encode()
            ).decode()
            if end < len(entries)
            else None
        )
        result = self.topology.envelope(
            "get_logs",
            node,
            data={
                "entries": page,
                "next_cursor": next_cursor,
                "revision": revision,
                "source": "container",
                "window_start": window,
                "window_end": collected,
                "limit": limit,
                "retained_count": len(entries),
            },
            error=error,
        )
        result["collected_at"] = collected
        result["truncated"] = truncated
        return result
