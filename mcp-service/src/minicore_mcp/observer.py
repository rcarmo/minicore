"""Volatile routing observer primitives. No persistence, packet buffers or client-owned collectors."""

import asyncio
import ipaddress
import json
import math
import re
import sys
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import uuid4

SCOPES = re.compile(
    r"(?:node:[a-z][a-z0-9]{1,15}|link:[a-z0-9-]{3,40}):(interfaces|routing|igmp)\Z"
)
HEALTH = {
    "ok",
    "collection_timeout",
    "collection_failed",
    "invalid_observation",
    "source_unavailable",
}


def encoded(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def integer(value, maximum=(1 << 64) - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid_observation")


def address(value, multicast=False):
    if not isinstance(value, str):
        raise ValueError("invalid_observation")
    ip = ipaddress.IPv4Address(value)
    if multicast and not ip.is_multicast:
        raise ValueError("invalid_observation")


def validate(kind, data):
    """Accept only structured network fields; no raw command output or arbitrary payload keys."""
    if not isinstance(data, dict):
        raise ValueError("invalid_observation")
    if kind == "interfaces":
        if (
            set(data) != {"interfaces"}
            or not isinstance(data["interfaces"], list)
            or len(data["interfaces"]) > 32
        ):
            raise ValueError("invalid_observation")
        fields = {
            "interface",
            "tx_packets",
            "rx_packets",
            "tx_bytes",
            "rx_bytes",
            "tx_errors",
            "rx_errors",
            "tx_drops",
            "rx_drops",
            "state",
        }
        for item in data["interfaces"]:
            if (
                not isinstance(item, dict)
                or set(item) - fields
                or not {"interface", "state"} <= set(item)
            ):
                raise ValueError("invalid_observation")
            if (
                not isinstance(item["interface"], str)
                or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}", item["interface"])
                or item["state"]
                not in {
                    "UP",
                    "DOWN",
                    "UNKNOWN",
                    "LOWERLAYERDOWN",
                    "DORMANT",
                    "NOTPRESENT",
                    "TESTING",
                }
            ):
                raise ValueError("invalid_observation")
            for key, value in item.items():
                if key not in {"interface", "state"}:
                    integer(value)
    elif kind == "routing":
        if (
            set(data) != {"peers", "routes"}
            or not isinstance(data["peers"], list)
            or not isinstance(data["routes"], list)
            or len(data["peers"]) > 64
            or len(data["routes"]) > 32
        ):
            raise ValueError("invalid_observation")
        for peer in data["peers"]:
            if (
                not isinstance(peer, dict)
                or set(peer) != {"protocol", "address", "state"}
                or peer["protocol"] not in {"bgp", "ospf"}
            ):
                raise ValueError("invalid_observation")
            address(peer["address"])
            if peer["state"] not in {
                "Idle",
                "Connect",
                "Active",
                "OpenSent",
                "OpenConfirm",
                "Established",
                "Deleted",
                "Clearing",
                "Down",
                "Attempt",
                "Init",
                "2-Way",
                "ExStart",
                "Exchange",
                "Loading",
                "Full",
                "Unknown",
            }:
                raise ValueError("invalid_observation")
        for route in data["routes"]:
            if (
                not isinstance(route, dict)
                or set(route) != {"prefix", "source", "nexthops"}
                or route["source"] not in {"bgp", "rib", "fib"}
            ):
                raise ValueError("invalid_observation")
            ipaddress.IPv4Network(route["prefix"], strict=True)
            if not isinstance(route["nexthops"], list) or len(route["nexthops"]) > 16:
                raise ValueError("invalid_observation")
            for hop in route["nexthops"]:
                address(hop)
    elif kind == "igmp":
        if set(data) != {
            "version",
            "message_type",
            "group",
            "reporter",
            "querier",
            "sources",
            "records",
        }:
            raise ValueError("invalid_observation")
        if data["version"] not in {1, 2, 3} or data["message_type"] not in {
            "query",
            "report",
            "report_v3",
            "report_v1",
            "report_v2",
            "leave",
        }:
            raise ValueError("invalid_observation")
        for field in ("group", "reporter", "querier"):
            if data[field] is not None:
                address(data[field], multicast=field == "group")
        if (
            not isinstance(data["sources"], list)
            or len(data["sources"]) > 64
            or not isinstance(data["records"], list)
            or len(data["records"]) > 64
        ):
            raise ValueError("invalid_observation")
        for source in data["sources"]:
            address(source)
        for record in data["records"]:
            if (
                not isinstance(record, dict)
                or set(record) != {"record_type", "group", "sources"}
                or type(record["record_type"]) is not int
                or record["record_type"] not in range(1, 7)
                or not isinstance(record["sources"], list)
                or len(record["sources"]) > 64
            ):
                raise ValueError("invalid_observation")
            address(record["group"], multicast=True)
            for source in record["sources"]:
                address(source)
    else:
        raise ValueError("invalid_kind")


class Store:
    """Bound encoded content plus conservative container overhead; no disk or long-lived delta cache."""

    def __init__(
        self,
        lab_id,
        generation,
        *,
        clock=time.monotonic,
        max_bytes=8 * 1024 * 1024,
        max_records=1024,
    ):
        if not 512 <= max_bytes <= 8 * 1024 * 1024 or not 1 <= max_records <= 1024:
            raise ValueError("invalid_limits")
        self.lab_id = lab_id
        self.generation = generation
        self.clock = clock
        self.max_bytes = max_bytes
        self.max_records = max_records
        self.epoch = str(uuid4())
        self._rows: deque[tuple[str, float, bytes, int]] = deque()
        self._scopes: dict[str, tuple[str, str, float]] = {}
        self._bytes = 0
        self.missed = 0

    def _scope(self, scope):
        if not isinstance(scope, str) or not SCOPES.fullmatch(scope):
            raise ValueError("invalid_scope")
        if scope not in self._scopes and len(self._scopes) >= 128:
            raise ValueError("scope_limit")

    def sweep(self):
        now = self.clock()
        # Delayed IPC may arrive out of order; expiry cannot rely on deque order.
        self._rows = deque(row for row in self._rows if 0 <= now - row[1] < 60)
        self._bytes = sum(row[3] for row in self._rows)
        self._scopes = {
            key: value for key, value in self._scopes.items() if 0 <= now - value[2] < 60
        }

    @property
    def record_count(self):
        self.sweep()
        return len(self._rows)

    @property
    def byte_size(self):
        self.sweep()
        return self._bytes

    def _missed(self):
        self.missed = min((1 << 53) - 1, self.missed + 1)

    def health(self, scope, state, incarnation):
        self.sweep()
        self._scope(scope)
        if (
            state not in HEALTH
            or not isinstance(incarnation, str)
            or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,128}", incarnation)
        ):
            raise ValueError("invalid_source")
        old = self._scopes.get(scope)
        if old and old[0] != incarnation:
            self._rows = deque(row for row in self._rows if row[0] != scope)
            self._bytes = sum(row[3] for row in self._rows)
        self._scopes[scope] = (incarnation, state, self.clock())

    def put(self, scope, data, *, acquired, incarnation):
        self.sweep()
        self._scope(scope)
        if (
            type(acquired) not in {int, float}
            or not math.isfinite(acquired)
            or acquired > self.clock()
        ):
            raise ValueError("invalid_acquisition_time")
        if self.clock() - acquired >= 60:
            self._missed()
            return False
        validate(scope.rsplit(":", 1)[-1], data)
        self.health(scope, "ok", incarnation)
        row = {
            "scope": scope,
            "incarnation": incarnation,
            "acquired_monotonic": acquired,
            "sampled_at": datetime.fromtimestamp(
                time.time() - (self.clock() - acquired), timezone.utc
            ).isoformat(),
            "data": data,
        }
        payload = encoded(row)
        cost = sys.getsizeof(payload) + sys.getsizeof(scope) + 256
        if len(payload) > 60000 or cost > self.max_bytes:
            self._missed()
            return False
        while self._rows and (
            len(self._rows) >= self.max_records or self._bytes + cost > self.max_bytes
        ):
            old = self._rows.popleft()
            self._bytes -= old[3]
            self._missed()
        self._rows.append((scope, acquired, payload, cost))
        self._bytes += cost
        return True

    def snapshot(self, scope, *, limit_bytes=65536):
        self.sweep()
        self._scope(scope)
        if not 512 <= limit_bytes <= 65536:
            raise ValueError("invalid_response_limit")
        now = self.clock()
        rows = sorted((row for row in self._rows if row[0] == scope), key=lambda row: row[1])
        result = {
            "lab_id": self.lab_id,
            "generation": self.generation,
            "observer_epoch": self.epoch,
            "scope": scope,
            "window_seconds": 60,
            "source_health": self._scopes.get(scope, (None, "source_unavailable"))[1],
            "missed_updates": self.missed,
            "truncated": False,
            "omitted": 0,
            "records": [],
        }
        selected = []
        for row in rows[-128:]:
            item = json.loads(row[2])
            item["remaining_ms"] = max(0, math.floor((60 - (now - row[1])) * 1000))
            selected.append(item)
        result["records"] = selected
        result["omitted"] = max(0, len(rows) - len(selected))
        result["truncated"] = bool(result["omitted"])
        while len(encoded(result)) > limit_bytes and selected:
            selected.pop(0)
            result["omitted"] += 1
            result["truncated"] = True
        if len(encoded(result)) > limit_bytes:
            raise ValueError("envelope_limit")
        return result

    def reset(self, generation):
        self.generation = generation
        self.epoch = str(uuid4())
        self._rows.clear()
        self._scopes.clear()
        self._bytes = 0
        self.missed = 0


class Coordinator:
    """Source lifetimes belong to the service, not individual HTTP/MCP callers."""

    def __init__(self, store, *, interval=5.0, timeout=10.0, concurrency=2):
        if interval <= 0 or timeout <= 0 or not 1 <= concurrency <= 8:
            raise ValueError("invalid_limits")
        self.store = store
        self.interval = interval
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(concurrency)
        self.sources: dict[str, Callable[[], Awaitable[tuple[dict, str]]]] = {}
        self.tasks: list[asyncio.Task] = []
        self._runner = None
        self._ready = asyncio.Event()

    def add(self, scope, collect):
        if self._runner is not None or scope in self.sources or len(self.sources) >= 128:
            raise ValueError("invalid_source_registration")
        self.store._scope(scope)
        self.sources[scope] = collect

    async def _source(self, scope, collect):
        while True:
            started = self.store.clock()
            epoch = self.store.epoch
            try:
                async with self.semaphore:
                    async with asyncio.timeout(self.timeout):
                        data, incarnation = await collect()
                    if epoch == self.store.epoch:
                        self.store.put(scope, data, acquired=started, incarnation=incarnation)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if epoch == self.store.epoch:
                    old = self.store._scopes.get(scope)
                    code = (
                        "collection_timeout"
                        if isinstance(exc, TimeoutError)
                        else "invalid_observation"
                        if isinstance(exc, ValueError)
                        else "collection_failed"
                    )
                    self.store.health(scope, code, old[0] if old else "unbound")
            await asyncio.sleep(self.interval)

    async def _sweep(self):
        while True:
            self.store.sweep()
            await asyncio.sleep(min(1.0, self.interval))

    async def _run(self):
        try:
            async with asyncio.TaskGroup() as group:
                self.tasks = [
                    group.create_task(self._source(scope, collect))
                    for scope, collect in self.sources.items()
                ]
                self.tasks.append(group.create_task(self._sweep()))
                self._ready.set()
                await asyncio.Event().wait()
        finally:
            self.tasks.clear()

    async def start(self):
        if self._runner is not None:
            return
        self._runner = asyncio.create_task(self._run())
        await self._ready.wait()

    async def close(self):
        if self._runner is not None:
            self._runner.cancel()
            await asyncio.gather(self._runner, return_exceptions=True)
            self._runner = None
            self._ready.clear()
        self.store.reset(self.store.generation)
