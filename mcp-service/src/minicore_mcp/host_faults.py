"""Inventory-derived host fault catalogue. No caller-provided argv or container names."""

import asyncio
import json
from pathlib import Path


def catalogue(inventory):
    result = {}
    for node in inventory["nodes"]:
        result["zap-node-" + node["id"]] = {
            "target_type": "node",
            "target_id": node["id"],
            "node_id": node["id"],
            "effect": "stop",
            "parameters": {},
        }
    for link in inventory["links"]:
        result["zap-link-" + link["id"]] = {
            "target_type": "link",
            "target_id": link["id"],
            "effect": "link_down",
            "parameters": {},
        }
    for kind, objects in [("node", inventory["nodes"]), ("link", inventory["links"])]:
        for obj in objects:
            for effect in ["delay", "loss"]:
                result[f"corrupt-{effect}-{kind}-{obj['id']}"] = {
                    "target_type": kind,
                    "target_id": obj["id"],
                    "effect": effect,
                    "parameters": {"delay_ms": 100} if effect == "delay" else {"loss_percent": 25},
                }
    for node in inventory["nodes"]:
        if node["kind"] == "router":
            result["corrupt-route-node-" + node["id"]] = {
                "target_type": "node",
                "target_id": node["id"],
                "node_id": node["id"],
                "effect": "blackhole",
                "parameters": {
                    "prefix": "10.200.9.0/29" if node["id"] != "ce2" else "10.200.8.0/29"
                },
            }
    return result


def endpoints(inventory, spec):
    if spec["target_type"] == "link":
        return next(
            link["endpoints"] for link in inventory["links"] if link["id"] == spec["target_id"]
        )
    return [
        e
        for link in inventory["links"]
        for e in link["endpoints"]
        if e["node"] == spec["target_id"]
    ]


def commands(inventory, scenario, action):
    specs = catalogue(inventory)
    if scenario not in specs or action not in {"apply", "reset"}:
        raise ValueError("denied_operation")
    spec = specs[scenario]
    nodes = {n["id"]: n for n in inventory["nodes"]}

    def container(node):
        return "minicore-" + nodes[node]["service"] + "-1"

    if spec["effect"] == "stop":
        return (
            [["docker", "stop", "--time", "2", container(spec["target_id"])]]
            if action == "apply"
            else [["docker", "start", container(spec["target_id"])]]
        )
    if spec["effect"] == "blackhole":
        return [
            [
                "docker",
                "exec",
                container(spec["target_id"]),
                "ip",
                "route",
                "add" if action == "apply" else "del",
                "blackhole",
                spec["parameters"]["prefix"],
                "metric",
                "42760",
                "proto",
                "186",
            ]
        ]
    rows = []
    for e in endpoints(inventory, spec):
        base = ["docker", "exec", container(e["node"])]
        if spec["effect"] == "link_down":
            rows.append(
                base
                + [
                    "ip",
                    "link",
                    "set",
                    "dev",
                    e["interface"],
                    "down" if action == "apply" else "up",
                ]
            )
        elif action == "reset":
            rows.append(
                base + ["tc", "qdisc", "del", "dev", e["interface"], "root", "handle", "1234:"]
            )
        else:
            rows.append(
                base
                + ["tc", "qdisc", "add", "dev", e["interface"], "root", "handle", "1234:", "netem"]
                + (["delay", "100ms"] if spec["effect"] == "delay" else ["loss", "25%"])
            )
    return rows


class HostAdapter:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path

    async def mutate(self, scenario, action):
        writer = None
        try:
            async with asyncio.timeout(20):
                reader, writer = await asyncio.open_unix_connection(
                    str(self.socket_path), limit=8192
                )
                writer.write(json.dumps({"scenario": scenario, "action": action}).encode() + b"\n")
                await writer.drain()
                raw = await reader.readline()
                if len(raw) > 4096:
                    raise ValueError()
                result = json.loads(raw)
                if (
                    set(result) - {"ok", "verified", "error_code"}
                    or type(result.get("ok")) is not bool
                    or type(result.get("verified")) is not bool
                ):
                    raise ValueError()
                return result
        except (OSError, ValueError, TimeoutError):
            return {"ok": False, "verified": False, "error_code": "host_controller_unavailable"}
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()


class CombinedExecutor:
    def __init__(self, legacy, host, inventory):
        self.legacy, self.host, self.inventory = legacy, host, inventory

    async def verify_baseline(self):
        return await self.legacy.verify_baseline()

    async def mutate(self, scenario, action):
        return await (self.host if scenario in catalogue(self.inventory) else self.legacy).mutate(
            scenario, action
        )


def decode(raw, inventory):
    if len(raw) > 1024:
        raise ValueError("invalid_arguments")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or set(value) != {"scenario", "action"}
        or not isinstance(value["scenario"], str)
        or value["scenario"] not in catalogue(inventory)
        or value["action"] not in {"apply", "reset"}
    ):
        raise ValueError("denied_operation")
    return value
