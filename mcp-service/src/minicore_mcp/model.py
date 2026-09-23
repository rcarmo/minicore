"""Declarative inventory plus explicitly sourced container observations."""

import copy
import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Topology:
    def __init__(self, inventory: Path, observations: Path):
        self.inventory = json.loads(inventory.read_text())
        self.observations = observations
        self.validate()
        self.nodes = {n["id"]: n for n in self.inventory["nodes"]}
        self._snapshot: dict | None = None

    def validate(self):
        t = self.inventory
        if t["schema_version"] != "1.0" or type(t["generation"]) is not int or t["generation"] < 1:
            raise ValueError("Invalid inventory schema/generation")
        ids = [n["id"] for n in t["nodes"]]
        if len(ids) != len(set(ids)) or not all(
            re.fullmatch("[a-z][a-z0-9]{1,15}", x) for x in ids
        ):
            raise ValueError("Invalid node identity")
        networks = [ipaddress.ip_network(t["management"]["subnet"])]
        endpoints = set()
        for link in t["links"]:
            network = ipaddress.ip_network(link["subnet"])
            if any(network.overlaps(other) for other in networks):
                raise ValueError("Overlapping topology networks")
            networks.append(network)
            addresses = {link["bridge_gateway"]}
            if len(link["endpoints"]) != 2 or len({e["node"] for e in link["endpoints"]}) != 2:
                raise ValueError("A data link requires two distinct endpoints")
            for e in link["endpoints"]:
                key = e["node"], e["interface"]
                address = ipaddress.ip_interface(e["address"])
                if (
                    e["node"] not in ids
                    or not re.fullmatch(r"[a-z][a-z0-9-]{1,14}", e["interface"])
                    or key in endpoints
                    or str(address.ip) in addresses
                    or address.network != network
                ):
                    raise ValueError("Invalid link endpoint")
                endpoints.add(key)
                addresses.add(str(address.ip))

    def snapshot(self):
        observed = {}
        runtime_status = "not_configured"
        try:
            if self.observations.stat().st_size > 65536:
                raise ValueError("Observation file too large")
            payload = json.loads(self.observations.read_text())
            if not isinstance(payload, dict):
                raise ValueError("Invalid observations")
            if (
                payload["lab_id"] != self.inventory["lab_id"]
                or payload["generation"] != self.inventory["generation"]
            ):
                raise ValueError("Observation identity mismatch")
            age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(payload["collected_at"].replace("Z", "+00:00"))
            ).total_seconds()
            if not -5 <= age <= 45:
                runtime_status = "unavailable"
            else:
                observed = payload["nodes"]
                if not isinstance(observed, dict) or any(
                    key not in self.nodes
                    or not isinstance(value, dict)
                    or set(value) != {"container_state"}
                    or not isinstance(value["container_state"], str)
                    for key, value in observed.items()
                ):
                    raise ValueError("Invalid observations")
                runtime_status = "available" if len(observed) == len(self.nodes) else "partial"
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, TypeError, OSError, AttributeError):
            observed = {}
            runtime_status = "unavailable"
        nodes = []
        for n in self.inventory["nodes"]:
            o = observed.get(n["id"], {})
            container_state = o.get("container_state", "unknown")
            if container_state not in {
                "running",
                "exited",
                "created",
                "paused",
                "restarting",
                "missing",
                "unknown",
            }:
                container_state = "unknown"
            # Container running is not proof of router/interface health.
            nodes.append(
                {k: n[k] for k in ("id", "label", "role", "kind", "position", "protocols")}
                | {
                    "expected": True,
                    "state": "unavailable"
                    if container_state in {"exited", "missing"}
                    else "unknown",
                    "container_state": container_state,
                    "observed_at": payload["collected_at"] if o else None,
                    "management_address": n.get("management_address"),
                }
            )
        links = [
            {
                "id": link["id"],
                "source": link["endpoints"][0]["node"],
                "target": link["endpoints"][1]["node"],
                "kind": "data",
                "state": "unknown",
                "expected": True,
                "observed_at": None,
                "endpoints": link["endpoints"],
            }
            for link in self.inventory["links"]
        ]
        result = {
            "schema_version": "1.0",
            "lab_id": self.inventory["lab_id"],
            "generation": self.inventory["generation"],
            "source": "combined",
            "runtime_status": runtime_status,
            "nodes": nodes,
            "links": links,
        }
        revision = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
        if self._snapshot is None or self._snapshot["revision"] != revision:
            self._snapshot = result | {"revision": revision, "collected_at": utc_now()}
        return copy.deepcopy(self._snapshot)

    def envelope(self, operation, node_id=None, *, data=None, error=None, request_id=None):
        from uuid import uuid4

        return {
            "schema_version": "1.0",
            "request_id": request_id or str(uuid4()),
            "lab_id": self.inventory["lab_id"],
            "generation": self.inventory["generation"],
            "node_id": node_id,
            "operation": operation,
            "collected_at": utc_now(),
            "duration_ms": 0,
            "status": "unavailable" if error else "ok",
            "data": data,
            "raw_evidence": "",
            "truncated": False,
            "error_code": error,
        }
