"""Async fixed-scope host observer discovery for Minicore Linux interface counters."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import socket
import struct
import time
from collections.abc import Awaitable, Callable, Iterable

NETLINK_ROUTE = 0
NLM_F_REQUEST = 1
NLM_F_ROOT = 0x100
NLM_F_MATCH = 0x200
NLMSG_DONE = 3
RTM_GETLINK = 18
RTM_NEWLINK = 16
IFLA_IFNAME = 3
IFLA_LINK = 5
IFLA_MASTER = 10
IFLA_STATS64 = 23
_ALLOWED = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_KEYS = (
    ("tx_packets", "rx_packets"),
    ("rx_packets", "tx_packets"),
    ("tx_bytes", "rx_bytes"),
    ("rx_bytes", "tx_bytes"),
    ("tx_errors", "rx_errors"),
    ("rx_errors", "tx_errors"),
    ("tx_drops", "rx_dropped"),
    ("rx_drops", "tx_dropped"),
)
_STATS = (
    "rx_packets",
    "tx_packets",
    "rx_bytes",
    "tx_bytes",
    "rx_errors",
    "tx_errors",
    "rx_dropped",
    "tx_dropped",
)


async def run_command(argv: list[str], *, timeout: float = 5.0, limit: int = 65536) -> str:
    proc = None
    readers: list[asyncio.Task] = []
    total = 0

    async def read(stream: asyncio.StreamReader) -> bytes:
        nonlocal total
        data = bytearray()
        while True:
            chunk = await stream.read(8192)
            if not chunk:
                return bytes(data)
            total += len(chunk)
            if total > limit:
                raise OverflowError("output_limit")
            data.extend(chunk)

    try:
        async with asyncio.timeout(timeout):
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            assert proc.stdout and proc.stderr
            readers = [
                asyncio.create_task(read(proc.stdout)),
                asyncio.create_task(read(proc.stderr)),
            ]
            out, err = await asyncio.gather(*readers)
            code = await proc.wait()
            if code:
                raise RuntimeError("command_failed")
            return out.decode(errors="replace")
    except TimeoutError as exc:
        raise TimeoutError("execution_timeout") from exc
    finally:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
        for task in readers:
            if not task.done():
                task.cancel()
        if readers:
            await asyncio.gather(*readers, return_exceptions=True)


async def dump_links(
    *,
    loader: Callable[[], Iterable[bytes]] | None = None,
    timeout: float = 1.0,
    limit: int = 262144,
) -> dict[int, dict]:
    if loader is not None:
        data = b"".join(loader())
        if len(data) > limit:
            raise ValueError("netlink_oversize")
        return _parse_links(data)
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, NETLINK_ROUTE)
    sock.setblocking(False)
    parts = []
    try:
        sock.bind((0, 0))
        sock.connect((0, 0))
        request = struct.pack(
            "IHHII", 32, RTM_GETLINK, NLM_F_REQUEST | NLM_F_ROOT | NLM_F_MATCH, 1, 0
        )
        request += struct.pack("BBHiII", socket.AF_UNSPEC, 0, 0, 0, 0, 0)
        await loop.sock_sendall(sock, request)
        total = 0
        deadline = loop.time() + timeout
        while True:
            remain = deadline - loop.time()
            if remain <= 0:
                raise TimeoutError("netlink_timeout")
            chunk = await asyncio.wait_for(loop.sock_recv(sock, 65536), remain)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError("netlink_oversize")
            parts.append(chunk)
            if _contains_done(chunk):
                break
        return _parse_links(b"".join(parts))
    finally:
        sock.close()


async def collect_interfaces(
    inventory: dict,
    *,
    run_command: Callable[..., Awaitable[str]] = run_command,
    netlink_reader: Callable[[], Awaitable[dict[int, dict]]] = dump_links,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, dict]:
    nodes = {n["id"]: n for n in inventory["nodes"]}
    endpoints: dict[str, list[dict]] = {node_id: [] for node_id in nodes}
    for link in inventory["links"]:
        for endpoint in link["endpoints"]:
            endpoints[endpoint["node"]].append(endpoint | {"network": link["network"]})
    active = {node_id: rows for node_id, rows in endpoints.items() if rows}
    names = {node_id: f"minicore-{nodes[node_id]['service']}-1" for node_id in active}
    networks = sorted({row["network"] for rows in active.values() for row in rows})
    acquired = clock()
    results: dict[str, dict] = {}
    semaphore = asyncio.Semaphore(2)
    try:
        network_raw, host_links = await asyncio.gather(
            run_command(
                ["docker", "network", "inspect", *["minicore_" + name for name in networks]],
                timeout=5.0,
                limit=65536,
            ),
            netlink_reader(),
        )
        bridges = _bridges(json.loads(network_raw), networks)
    except TimeoutError:
        return {
            node_id: {"acquired": acquired, "error_code": "execution_timeout"} for node_id in active
        }
    except (RuntimeError, ValueError, TypeError, OSError, OverflowError):
        return {
            node_id: {"acquired": acquired, "error_code": "discovery_failed"} for node_id in active
        }

    async def per_node(node_id: str, rows: list[dict]):
        try:
            async with semaphore:
                raw = await run_command(
                    ["docker", "inspect", names[node_id]], timeout=5.0, limit=65536
                )
                containers = _containers(json.loads(raw))
                container = containers[names[node_id]]
                labels = container["labels"]
                if (
                    labels.get("io.minicore.node") != node_id
                    or labels.get("io.minicore.lab") != inventory["lab_id"]
                    or labels.get("com.docker.compose.project") != "minicore"
                    or labels.get("com.docker.compose.service") != nodes[node_id]["service"]
                ):
                    raise ValueError("identity_mismatch")
                if container["running"] is not True:
                    raise ValueError("node_stopped")
                if nodes[node_id]["kind"] == "endpoint":
                    links: dict[str, dict] = {}
                    for row in rows:
                        interface = row["interface"]
                        if not re.fullmatch(r"to-[a-z0-9]{2,15}", interface):
                            raise ValueError("invalid_interface")
                        base = "/sys/class/net/" + interface + "/"
                        raw = await run_command(
                            [
                                "docker",
                                "exec",
                                names[node_id],
                                "cat",
                                base + "ifindex",
                                base + "iflink",
                                base + "operstate",
                            ],
                            timeout=5.0,
                            limit=65536,
                        )
                        fields = raw.strip().splitlines()
                        if len(fields) != 3:
                            raise ValueError("endpoint_unmapped")
                        links[interface] = {
                            "ifindex": int(fields[0]),
                            "link_index": int(fields[1]),
                            "operstate": fields[2].upper(),
                        }
                else:
                    links = await _container_links(run_command, names[node_id])
            data = []
            internal = []
            for row in rows:
                item = links.get(row["interface"])
                if (
                    not item
                    or type(item.get("ifindex")) is not int
                    or type(item.get("link_index")) is not int
                ):
                    raise ValueError("endpoint_unmapped")
                network_id = container["networks"].get("minicore_" + row["network"])
                if not isinstance(network_id, str):
                    raise ValueError("network_unmapped")
                bridge = bridges.get(network_id)
                if not bridge:
                    raise ValueError("network_unmapped")
                host = _match_host(host_links, bridge, item["ifindex"], item["link_index"])
                if host is None:
                    raise ValueError("endpoint_unmapped")
                data.append(
                    _normalize(row["interface"], item.get("operstate", "UNKNOWN"), host["stats"])
                )
                internal.append(
                    {
                        "interface": row["interface"],
                        "container_ifindex": item["ifindex"],
                        "container_peer_ifindex": item["link_index"],
                        "host_ifindex": host["ifindex"],
                        "host_bridge_ifindex": bridge["ifindex"],
                    }
                )
            internal.sort(key=lambda x: x["interface"])
            incarnation = f"{container['id']}:{'-'.join(str(x['host_ifindex']) for x in internal)}"
            if not _ALLOWED.fullmatch(incarnation):
                raise ValueError("invalid_incarnation")
            results[node_id] = {
                "acquired": acquired,
                "incarnation": incarnation,
                "data": {"interfaces": sorted(data, key=lambda x: x["interface"])},
                "_internal": {"container_id": container["id"], "mappings": internal},
            }
        except KeyError:
            results[node_id] = {"acquired": acquired, "error_code": "container_missing"}
        except (TypeError, ValueError) as exc:
            results[node_id] = {"acquired": acquired, "error_code": str(exc)}
        except TimeoutError:
            results[node_id] = {"acquired": acquired, "error_code": "execution_timeout"}
        except (RuntimeError, OSError, OverflowError):
            results[node_id] = {"acquired": acquired, "error_code": "command_failed"}

    await asyncio.gather(*(per_node(node_id, rows) for node_id, rows in active.items()))
    return results


async def _container_links(
    run_command: Callable[..., Awaitable[str]], name: str
) -> dict[str, dict]:
    raw = await run_command(
        ["docker", "exec", name, "ip", "-j", "link", "show"], timeout=5.0, limit=65536
    )
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise ValueError("command_failed")
    return {
        row["ifname"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("ifname"), str)
    }


def _containers(rows: list[dict]) -> dict[str, dict]:
    result = {}
    if not isinstance(rows, list):
        raise ValueError("identity_mismatch")
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("Name"), str)
            or not isinstance(row.get("Id"), str)
        ):
            raise ValueError("command_failed")
        networks = row.get("NetworkSettings", {}).get("Networks", {})
        if not isinstance(networks, dict):
            raise ValueError("command_failed")
        result[row["Name"].removeprefix("/")] = {
            "id": row["Id"],
            "labels": row.get("Config", {}).get("Labels", {}) or {},
            "running": row.get("State", {}).get("Running"),
            "networks": {
                name: data.get("NetworkID")
                for name, data in networks.items()
                if isinstance(name, str) and isinstance(data, dict)
            },
        }
    return result


def _bridges(rows: list[dict], expected: list[str]) -> dict[str, dict]:
    result = {}
    if not isinstance(rows, list):
        raise ValueError("network_identity_mismatch")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("Id"), str):
            raise ValueError("command_failed")
        labels = row.get("Labels") or {}
        logical = labels.get("com.docker.compose.network")
        if (
            logical not in expected
            or labels.get("com.docker.compose.project") != "minicore"
            or row.get("Name") != "minicore_" + logical
            or row.get("Driver") != "bridge"
        ):
            raise ValueError("network_identity_mismatch")
        options = row.get("Options") or {}
        if not isinstance(options, dict):
            raise ValueError("command_failed")
        name = options.get("com.docker.network.bridge.name") or ("br-" + row["Id"][:12])
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name):
            raise ValueError("network_identity_mismatch")
        result[row["Id"]] = {"name": name, "ifindex": None}
    if len(result) != len(expected):
        raise ValueError("network_identity_mismatch")
    return result


def _match_host(
    host_links: dict[int, dict], bridge: dict, container_ifindex: int, container_peer: int
) -> dict | None:
    for link in host_links.values():
        if link.get("name") == bridge["name"]:
            bridge["ifindex"] = link["ifindex"]
            break
    if not isinstance(bridge.get("ifindex"), int):
        return None
    for link in host_links.values():
        if (
            link.get("master") == bridge["ifindex"]
            and link.get("peer") == container_ifindex
            and link.get("ifindex") == container_peer
        ):
            return link
    return None


def _normalize(interface: str, state: str, stats: dict) -> dict:
    if not isinstance(stats, dict) or any(key not in stats for key in _STATS):
        raise ValueError("counters_unavailable")
    if state not in {"UP", "DOWN", "UNKNOWN", "DORMANT", "LOWERLAYERDOWN", "NOTPRESENT", "TESTING"}:
        raise ValueError("state_unavailable")
    result: dict = {"interface": interface, "state": state}
    for target, source in _KEYS:
        result[target] = _u64(stats[source])
    return result


def _u64(value: object) -> int:
    if type(value) is not int or not 0 <= value <= (1 << 64) - 1:
        raise ValueError("command_failed")
    return value


def _contains_done(data: bytes) -> bool:
    offset = 0
    while offset + 16 <= len(data):
        length, msg_type, _, _, _ = struct.unpack_from("IHHII", data, offset)
        if length < 16 or offset + length > len(data):
            return False
        if msg_type == NLMSG_DONE:
            return True
        offset += (length + 3) & ~3
    return False


def _parse_links(data: bytes) -> dict[int, dict]:
    links: dict[int, dict] = {}
    offset = 0
    done = False
    while offset + 16 <= len(data):
        length, msg_type, flags, sequence, _ = struct.unpack_from("IHHII", data, offset)
        if done or length < 16 or offset + length > len(data) or flags & 0x10 or sequence != 1:
            raise ValueError("netlink_malformed")
        body = data[offset + 16 : offset + length]
        if msg_type == NLMSG_DONE:
            if body and (len(body) < 4 or struct.unpack_from("i", body)[0] != 0):
                raise ValueError("netlink_error")
            done = True
        elif msg_type == 2:
            raise ValueError("netlink_error")
        elif msg_type == RTM_NEWLINK:
            _parse_link(body, links)
        else:
            raise ValueError("netlink_unexpected")
        offset += (length + 3) & ~3
    if not done or offset != len(data):
        raise ValueError("netlink_incomplete")
    return links


def _parse_link(body: bytes, links: dict[int, dict]) -> None:
    if len(body) < 16:
        raise ValueError("netlink_malformed")
    _, _, _, index, _, _ = struct.unpack_from("BBHiII", body, 0)
    attrs = {"ifindex": index, "stats": {}}
    offset = 16
    while offset + 4 <= len(body):
        size, kind = struct.unpack_from("HH", body, offset)
        if size < 4 or offset + size > len(body):
            raise ValueError("netlink_malformed")
        payload = body[offset + 4 : offset + size]
        if kind == IFLA_IFNAME and payload:
            attrs["name"] = payload.split(b"\x00", 1)[0].decode(errors="ignore")[:15]
        elif kind == IFLA_MASTER and len(payload) >= 4:
            attrs["master"] = struct.unpack_from("I", payload, 0)[0]
        elif kind == IFLA_LINK and len(payload) >= 4:
            attrs["peer"] = struct.unpack_from("I", payload, 0)[0]
        elif kind == IFLA_STATS64:
            if len(payload) < 8 * len(_STATS):
                raise ValueError("netlink_malformed")
            stats = {}
            bounded = payload[: 8 * len(_STATS)]
            for pos, key in enumerate(_STATS):
                start = pos * 8
                if start + 8 <= len(bounded):
                    stats[key] = struct.unpack_from("Q", bounded, start)[0]
            attrs["stats"] = stats
        offset += (size + 3) & ~3
    if offset != len(body):
        raise ValueError("netlink_malformed")
    if "name" in attrs:
        if index in links:
            raise ValueError("netlink_duplicate")
        links[index] = attrs
