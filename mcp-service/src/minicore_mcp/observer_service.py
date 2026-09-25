"""Read-only volatile observer Unix service and shared management source coordinator."""

import asyncio
import hashlib
import json
import os
import socket
import struct
import time
from pathlib import Path

from .observer import Coordinator, Store, encoded, validate
from .observer_host import collect_interfaces, dump_links
from .routing import prefixes


class CounterService:
    def __init__(self, inventory, path, *, allowed_uid=10001, clock=time.monotonic, capture=False):
        self.inventory = inventory
        self.path = Path(path)
        self.allowed_uid = allowed_uid
        self.clock = clock
        self.store = Store(inventory["lab_id"], inventory["generation"], clock=clock)
        self.nodes = {n["id"] for n in inventory["nodes"]}
        self.mappings = {}
        self.server = None
        self.tasks = []
        self.clients = set()
        self.last_discovery = -60.0
        from .igmp_capture import Capture

        self.capture = Capture(self.store, clock=clock) if capture else None

    def ingest(self, values):
        for node, row in values.items():
            if node not in self.nodes:
                continue
            scope = f"node:{node}:interfaces"
            if row.get("error_code"):
                old = self.store._scopes.get(scope)
                self.store.health(scope, "source_unavailable", old[0] if old else "unbound")
                self.mappings.pop(node, None)
                continue
            incarnation = hashlib.sha256(row["incarnation"].encode()).hexdigest()[:24]
            accepted = self.store.put(
                scope, row["data"], acquired=row["acquired"], incarnation=incarnation
            )
            if not accepted:
                continue
            if row.get("_internal"):
                self.mappings[node] = row

    async def _sample(self):
        while True:
            began = self.clock()
            try:
                if began - self.last_discovery >= 5 or not self.mappings:
                    self.ingest(await collect_interfaces(self.inventory, clock=self.clock))
                    self.last_discovery = began
                else:
                    links = await dump_links()
                    from .observer_host import _normalize

                    for node, old in list(self.mappings.items()):
                        data = []
                        try:
                            for mapping in old["_internal"]["mappings"]:
                                host = links[mapping["host_ifindex"]]
                                if (
                                    host.get("peer") != mapping["container_ifindex"]
                                    or host.get("master") != mapping["host_bridge_ifindex"]
                                ):
                                    raise ValueError()
                                # Container operstate is refreshed by discovery every 5s.
                                state = next(
                                    i["state"]
                                    for i in old["data"]["interfaces"]
                                    if i["interface"] == mapping["interface"]
                                )
                                data.append(_normalize(mapping["interface"], state, host["stats"]))
                            incarnation = hashlib.sha256(old["incarnation"].encode()).hexdigest()[
                                :24
                            ]
                            self.store.put(
                                f"node:{node}:interfaces",
                                {"interfaces": data},
                                acquired=began,
                                incarnation=incarnation,
                            )
                        except (KeyError, ValueError, StopIteration):
                            self.mappings.pop(node, None)
                            self.store.health(
                                f"node:{node}:interfaces", "source_unavailable", "unbound"
                            )
                            self.last_discovery = -60.0
            except asyncio.CancelledError:
                raise
            except Exception:
                self.mappings.clear()
                for node in self.nodes:
                    self.store.health(f"node:{node}:interfaces", "collection_failed", "unbound")
            if self.capture:
                bindings = []
                for node, row in self.mappings.items():
                    incarnation = hashlib.sha256(row["incarnation"].encode()).hexdigest()[:24]
                    for mapping in row["_internal"]["mappings"]:
                        bindings.append(
                            {
                                "node": node,
                                "interface": mapping["interface"],
                                "ifindex": mapping["host_ifindex"],
                                "host_name": mapping["host_name"],
                                "incarnation": incarnation,
                            }
                        )
                self.capture.reconcile(bindings)
                self.capture.poll_stats()
            await asyncio.sleep(max(0.1, 1 - (self.clock() - began)))

    async def _sweep(self):
        while True:
            self.store.sweep()
            now = self.clock()
            self.mappings = {
                node: row for node, row in self.mappings.items() if 0 <= now - row["acquired"] < 60
            }
            await asyncio.sleep(1)

    async def _client(self, reader, writer):
        task = asyncio.current_task()
        if len(self.clients) >= 16:
            writer.close()
            return
        self.clients.add(task)
        try:
            async with asyncio.timeout(3):
                raw_peer = writer.get_extra_info("socket").getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12
                )
                _, uid, _ = struct.unpack("3i", raw_peer)
                if uid != self.allowed_uid:
                    result = {"error_code": "denied_identity", "data": None}
                else:
                    raw = await reader.readline()
                    args = json.loads(raw)
                    if (
                        len(raw) > 512
                        or not isinstance(args, dict)
                        or set(args) not in ({"node_id"}, {"node_id", "kind"})
                        or args.get("kind", "interfaces") not in {"interfaces", "igmp"}
                        or not isinstance(args["node_id"], str)
                        or args["node_id"] not in self.nodes
                    ):
                        result = {"error_code": "invalid_scope", "data": None}
                    else:
                        kind = args.get("kind", "interfaces")
                        value = self.store.snapshot(f"node:{args['node_id']}:{kind}")
                        if kind == "igmp":
                            result = value
                        elif not value["records"] or value["source_health"] != "ok":
                            result = {"data": None, "error_code": "source_unavailable"}
                        else:
                            row = value["records"][-1]
                            result = {
                                "data": row["data"],
                                "acquired": row["acquired_monotonic"],
                                "incarnation": self.store.epoch + ":" + row["incarnation"],
                                "error_code": None,
                            }
                writer.write(encoded(result) + b"\n")
                await writer.drain()
        except (OSError, ValueError, TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            self.clients.discard(task)

    async def start(self, *, collect=True):
        # Directory ownership is provisioned outside the running event loop.
        self.server = await asyncio.start_unix_server(self._client, path=str(self.path), limit=1024)
        os.chmod(self.path, 0o660)
        if collect:
            self.tasks.append(asyncio.create_task(self._sample()))
        self.tasks.append(asyncio.create_task(self._sweep()))

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        if self.capture:
            self.capture.close()
        tasks = [*self.tasks, *self.clients]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        self.clients.clear()
        self.mappings.clear()
        self.store.reset(self.store.generation)
        await asyncio.to_thread(self.path.unlink, missing_ok=True)


class HostClient:
    def __init__(self, path):
        self.path = path

    async def read(self, node, kind="interfaces"):
        writer = None
        try:
            async with asyncio.timeout(4):
                reader, writer = await asyncio.open_unix_connection(str(self.path), limit=65537)
                writer.write(encoded({"node_id": node, "kind": kind}) + b"\n")
                await writer.drain()
                raw = await reader.readline()
                if len(raw) > 65536:
                    raise ValueError("output_limit")
                result = json.loads(raw)
                if kind == "igmp":
                    if (
                        not isinstance(result, dict)
                        or not isinstance(result.get("records"), list)
                        or len(result["records"]) > 128
                        or result.get("scope") != f"node:{node}:igmp"
                    ):
                        raise ValueError("invalid_observation")
                    for row in result["records"]:
                        validate("igmp", row["data"])
                    return result
                if not isinstance(result, dict) or set(result) - {
                    "data",
                    "acquired",
                    "incarnation",
                    "error_code",
                }:
                    raise ValueError("invalid_observation")
                if not result.get("error_code"):
                    validate("interfaces", result["data"])
                return result
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()


async def collect_router(topology, adapter, node):
    peers = {}
    routes = []
    for prefix in prefixes(topology):
        value = await adapter.execute(node, {"operation": "get_routing", "prefix": prefix})
        if value.get("error_code") or value.get("truncated"):
            raise RuntimeError("source_unavailable")
        data = value["data"]
        if data.get("prefix") != prefix:
            raise ValueError("invalid_observation")
        for address, row in data["bgp_peers"].get("ipv4Unicast", {}).get("peers", {}).items():
            peers[("bgp", address)] = {
                "protocol": "bgp",
                "address": address,
                "state": row.get("state", "Unknown"),
            }
        for address, rows in data["ospf_neighbors"].items():
            if isinstance(rows, list):
                for row in rows:
                    peers[("ospf", address)] = {
                        "protocol": "ospf",
                        "address": address,
                        "state": row.get("nbrState", "Unknown").split("/")[0],
                    }
        for source, entries in [
            ("bgp", data["bgp"].get("paths", [])),
            ("rib", data["rib"].get(prefix, [])),
            ("fib", data["fib"]),
        ]:
            hops = set()
            for row in entries:
                if source == "fib" and row.get("dst") != prefix:
                    continue
                if row.get("gateway"):
                    hops.add(row["gateway"])
                for hop in row.get("nexthops", []):
                    address = hop.get("ip") or hop.get("gateway")
                    if address:
                        hops.add(address)
            if entries:
                routes.append({"prefix": prefix, "source": source, "nexthops": sorted(hops)})
    result = {"peers": list(peers.values()), "routes": routes}
    validate("routing", result)
    return result, "routing-" + str(topology.inventory["generation"])


class ObserverRuntime:
    def __init__(self, topology, adapter, socket_path):
        self.topology = topology
        self.adapter = adapter
        self.store = Store(topology.inventory["lab_id"], topology.inventory["generation"])
        self.host = HostClient(socket_path)
        self.routing = Coordinator(self.store, interval=5, timeout=30, concurrency=2)
        if adapter:
            for node in topology.inventory["nodes"]:
                if node["kind"] == "router":
                    self.routing.add(
                        f"node:{node['id']}:routing",
                        lambda node=node: collect_router(topology, adapter, node["id"]),
                    )
        self.task = None

    async def _host_node(self, node):
        while True:
            if self.store.generation != self.topology.inventory["generation"]:
                self.store.reset(self.topology.inventory["generation"])
            epoch = self.store.epoch
            try:
                value = await self.host.read(node)
                if epoch == self.store.epoch:
                    if value.get("error_code"):
                        raise RuntimeError("source_unavailable")
                    scope = f"node:{node}:interfaces"
                    current = self.store.snapshot(scope)["records"]
                    if not current or current[-1]["acquired_monotonic"] != value["acquired"]:
                        self.store.put(
                            scope,
                            value["data"],
                            acquired=value["acquired"],
                            incarnation=value["incarnation"],
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                if epoch == self.store.epoch:
                    self.store.health(f"node:{node}:interfaces", "source_unavailable", "unbound")
            try:
                igmp = await self.host.read(node, kind="igmp")
                if epoch == self.store.epoch:
                    scope = f"node:{node}:igmp"
                    source = igmp.get("source_incarnation") or "unbound"
                    incarnation = igmp["observer_epoch"] + ":" + source
                    self.store.health(scope, igmp["source_health"], incarnation)
                    current = {
                        (r["incarnation"], r["acquired_monotonic"])
                        for r in self.store.snapshot(scope)["records"]
                    }
                    for row in igmp["records"]:
                        if row["incarnation"] != source:
                            continue
                        if (incarnation, row["acquired_monotonic"]) not in current:
                            self.store.put(
                                scope,
                                row["data"],
                                acquired=row["acquired_monotonic"],
                                incarnation=incarnation,
                            )
            except asyncio.CancelledError:
                raise
            except Exception:
                if epoch == self.store.epoch:
                    self.store.health(f"node:{node}:igmp", "source_unavailable", "unbound")
            await asyncio.sleep(1)

    async def _host_loop(self):
        async with asyncio.TaskGroup() as group:
            for node in self.topology.nodes:
                group.create_task(self._host_node(node))
            await asyncio.Event().wait()

    async def start(self):
        await self.routing.start()
        self.task = asyncio.create_task(self._host_loop())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        await self.routing.close()
