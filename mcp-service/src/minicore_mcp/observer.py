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
        required = {"version", "message_type", "group", "reporter", "querier", "sources", "records"}
        if not required <= set(data) or set(data) - required - {"node_id", "interface"}:
            raise ValueError("invalid_observation")
        for field in ("node_id", "interface"):
            if field in data and (
                not isinstance(data[field], str)
                or not re.fullmatch("[a-zA-Z0-9_.-]{1,32}", data[field])
            ):
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
        self.not_before = float("-inf")
        self._rows: deque[tuple[str, float, bytes, int]] = deque()
        self._scopes: dict[str, tuple[str, str, float]] = {}
        self._bytes = 0
        self.missed = 0
        self.revision = 0
        self._groups: dict[str, float] = {}
        self._loss: dict[str, dict[str, int]] = {}
        self._loss_buckets: dict[str, list[tuple[float, dict[str, int]]]] = {}

    def _scope(self, scope):
        if not isinstance(scope, str) or not SCOPES.fullmatch(scope):
            raise ValueError("invalid_scope")
        if scope not in self._scopes and len(self._scopes) >= 128:
            raise ValueError("scope_limit")

    def sweep(self):
        now = self.clock()
        # Delayed IPC may arrive out of order; expiry cannot rely on deque order.
        before = len(self._rows)
        self._rows = deque(row for row in self._rows if 0 <= now - row[1] < 60)
        if len(self._rows) != before:
            self.revision += 1
        self._bytes = sum(row[3] for row in self._rows)
        self._groups = {g: t for g, t in self._groups.items() if 0 <= now - t < 60}
        self._loss_buckets = {
            scope: [bucket for bucket in buckets if 0 <= now - bucket[0] < 60]
            for scope, buckets in self._loss_buckets.items()
        }
        self._loss_buckets = {
            scope: buckets for scope, buckets in self._loss_buckets.items() if buckets
        }
        self._loss = {}
        for scope, buckets in self._loss_buckets.items():
            total: dict[str, int] = {}
            for _, counts in buckets:
                for reason, count in counts.items():
                    total[reason] = min(2**53 - 1, total.get(reason, 0) + count)
            self._loss[scope] = total
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

    def drop(self, scope, reason, count=1):
        self._scope(scope)
        if reason not in {
            "expired",
            "overflow",
            "parse",
            "truncated",
            "checksum_partial",
            "socket_unavailable",
            "kernel_drops",
            "rate_limit",
        }:
            raise ValueError("invalid_loss_reason")
        integer(count, 2**53 - 1)
        if len(self._loss) >= 128 and scope not in self._loss:
            raise ValueError("scope_limit")
        stamp = math.floor(self.clock())
        buckets = self._loss_buckets.setdefault(scope, [])
        if not buckets or buckets[-1][0] != stamp:
            buckets.append((stamp, {}))
        counts = buckets[-1][1]
        counts[reason] = min(2**53 - 1, counts.get(reason, 0) + count)
        self.missed = min(2**53 - 1, self.missed + count)
        self.revision += 1
        self.sweep()

    def import_loss(self, scope, buckets):
        self._scope(scope)
        if not isinstance(buckets, list) or len(buckets) > 60:
            raise ValueError("invalid_loss")
        clean = []
        for bucket in buckets:
            if not isinstance(bucket, dict) or set(bucket) != {"acquired_monotonic", "counts"}:
                raise ValueError("invalid_loss")
            stamp = bucket["acquired_monotonic"]
            counts = bucket["counts"]
            if (
                type(stamp) not in {int, float}
                or not math.isfinite(stamp)
                or stamp > self.clock()
                or not isinstance(counts, dict)
                or len(counts) > 8
            ):
                raise ValueError("invalid_loss")
            for reason, count in counts.items():
                if reason not in {
                    "expired",
                    "overflow",
                    "parse",
                    "truncated",
                    "checksum_partial",
                    "socket_unavailable",
                    "kernel_drops",
                    "rate_limit",
                }:
                    raise ValueError("invalid_loss_reason")
                integer(count, 2**53 - 1)
            if 0 <= self.clock() - stamp < 60:
                clean.append((stamp, dict(counts)))
        self._loss_buckets[scope] = clean
        self.sweep()

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
        if old and (old[0] != incarnation or old[1] != "ok" and state == "ok"):
            self._rows = deque(row for row in self._rows if row[0] != scope)
            self._bytes = sum(row[3] for row in self._rows)
        self._scopes[scope] = (incarnation, state, self.clock())
        if not old or old[:2] != (incarnation, state):
            self.revision += 1

    def put(self, scope, data, *, acquired, incarnation):
        self.sweep()
        self._scope(scope)
        if (
            type(acquired) not in {int, float}
            or not math.isfinite(acquired)
            or acquired > self.clock()
        ):
            raise ValueError("invalid_acquisition_time")
        if acquired < self.not_before or self.clock() - acquired >= 60:
            self.drop(scope, "expired")
            return False
        kind = scope.rsplit(":", 1)[-1]
        validate(kind, data)
        if kind == "igmp":
            groups = {data["group"]} if data.get("group") else set()
            groups.update(row["group"] for row in data["records"])
            if len(set(self._groups) | groups) > 256:
                self.drop(scope, "overflow")
                return False
            for group in groups:
                self._groups[group] = acquired
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
            self.drop(scope, "overflow")
            return False
        while self._rows and (
            len(self._rows) >= self.max_records or self._bytes + cost > self.max_bytes
        ):
            old = self._rows.popleft()
            self._bytes -= old[3]
            self.drop(old[0], "overflow")
        self._rows.append((scope, acquired, payload, cost))
        self._bytes += cost
        self._scopes[scope] = (incarnation, "ok", acquired)
        self.revision += 1
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
            "source_incarnation": self._scopes.get(scope, (None,))[0],
            "missed_updates": sum(self._loss.get(scope, {}).values()),
            "capture_errors": dict(self._loss.get(scope, {})),
            "loss_buckets": [
                {"acquired_monotonic": stamp, "counts": counts}
                for stamp, counts in self._loss_buckets.get(scope, [])
            ],
            "truncated": False,
            "omitted": 0,
            "records": [],
        }
        health = self._scopes.get(scope)
        if (
            health
            and health[1] == "ok"
            and now - health[2] > (15 if scope.endswith(":routing") else 3)
        ):
            result["source_health"] = "collection_timeout"
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
        self.not_before = self.clock()
        self.generation = generation
        self.epoch = str(uuid4())
        self.revision += 1
        self._rows.clear()
        self._scopes.clear()
        self._groups.clear()
        self._loss.clear()
        self._loss_buckets.clear()
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


def selector(topology, args):
    if (
        not isinstance(args, dict)
        or args.get("scope") not in {"node", "link"}
        or args.get("observation") not in {"interfaces", "routing", "igmp"}
    ):
        raise ValueError("invalid_observer_scope")
    scope = args["scope"]
    key = "node_id" if scope == "node" else "link_id"
    if set(args) != {"scope", key, "observation"} or not isinstance(args[key], str):
        raise ValueError("invalid_observer_scope")
    ids = (
        topology.nodes if scope == "node" else {link["id"] for link in topology.inventory["links"]}
    )
    if args[key] not in ids or scope == "link" and args["observation"] == "routing":
        raise ValueError("invalid_observer_scope")
    return f"{scope}:{args[key]}:{args['observation']}"


def link_snapshot(store, topology, link_id, kind):
    link = next(link for link in topology.inventory["links"] if link["id"] == link_id)
    result = store.snapshot(f"link:{link_id}:{kind}")
    records = []
    states = []
    result["sources"] = {}
    result["capture_errors"] = {}
    result["missed_updates"] = 0
    for endpoint in link["endpoints"]:
        source = store.snapshot(f"node:{endpoint['node']}:{kind}")
        states.append(source["source_health"])
        result["missed_updates"] += source["missed_updates"]
        for reason, count in source.get("capture_errors", {}).items():
            result["capture_errors"][reason] = result["capture_errors"].get(reason, 0) + count
        result["sources"][endpoint["node"]] = source["source_health"]
        for row in source["records"]:
            if kind == "interfaces":
                interfaces = [
                    item | {"node_id": endpoint["node"]}
                    for item in row["data"]["interfaces"]
                    if item["interface"] == endpoint["interface"]
                ]
                if not interfaces:
                    continue
                data = {"interfaces": interfaces}
            else:
                if row["data"].get("interface") != endpoint["interface"]:
                    continue
                data = row["data"]
            records.append(
                row
                | {
                    "scope": result["scope"],
                    "incarnation": endpoint["node"] + ":" + row["incarnation"],
                    "data": data,
                }
            )
    records.sort(key=lambda r: r["acquired_monotonic"])
    result["source_health"] = (
        "ok"
        if states and all(s == "ok" for s in states)
        else next((s for s in states if s != "ok"), "source_unavailable")
    )
    result["records"] = records[-128:]
    result["omitted"] = max(0, len(records) - 128)
    result["partial"] = result["source_health"] != "ok"
    result["truncated"] = bool(result["omitted"])
    while len(encoded(result)) > 65536 and result["records"]:
        result["records"].pop(0)
        result["omitted"] += 1
        result["truncated"] = True
    return result
