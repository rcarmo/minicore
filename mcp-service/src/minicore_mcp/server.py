"""One uMCP listener: role-filtered MCP and read-only HTTP/SSE assets."""

import asyncio
import copy
import ipaddress
import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from aioumcp import AsyncMCPServer
from umcp_shared import MCPAuthenticationBusy, MCPHTTPResponse, get_request_context

from .activity import Activity
from .configuration import baseline
from .faults import SCENARIOS as FAULT_SPECS
from .faults import FaultController
from .file_io import FileIO
from .logs import LogStore
from .model import Topology
from .observer import Store, link_snapshot
from .observer import selector as observer_selector
from .policy import GOD, OPERATOR, Policy
from .routing import collect as collect_routing
from .routing import prefixes
from .ssh_adapter import SSHAdapter

SCENARIOS = ("core-link-failure", "customer-bgp-failure", "data-path-degradation")


def schema(properties=None, required=None):
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


STRING = {"type": "string", "maxLength": 128}
INPUTS = {
    "list_nodes": schema(),
    "get_evidence": schema(
        {
            "prefix": STRING,
            "kind": {
                "type": "string",
                "enum": ["topology", "logs", "configuration", "routing", "observer"],
            },
            "node_id": STRING,
            "scope": {"type": "string", "enum": ["node", "link"]},
            "observation": {"type": "string", "enum": ["interfaces", "routing", "igmp"]},
            "link_id": STRING,
            "file": STRING,
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": "string", "maxLength": 256},
        },
        ["kind"],
    ),
    "get_interfaces": schema({"node_id": STRING, "interface": STRING}, ["node_id"]),
    "get_routes": schema({"node_id": STRING, "prefix": STRING}, ["node_id"]),
    "get_neighbors": schema(
        {"node_id": STRING, "protocol": {"type": "string", "enum": ["bgp", "ospf"]}},
        ["node_id", "protocol"],
    ),
    "ping": schema(
        {
            "node_id": STRING,
            "destination": STRING,
            "count": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        ["node_id", "destination"],
    ),
    "list_fault_scenarios": schema(),
    "get_fault_state": schema(),
    "apply_fault": schema(
        {"scenario_id": {"type": "string", "enum": list(SCENARIOS)}, "idempotency_key": STRING},
        ["scenario_id", "idempotency_key"],
    ),
    "reset_lab": schema({"idempotency_key": STRING}, ["idempotency_key"]),
}


class AdmittedStream:
    """Own a subscriber slot even before the transport starts iteration."""

    def __init__(self, server, source):
        if server.streams >= 16:
            raise OSError("stream_limit")
        self.server = server
        self.source = source
        self.closed = False
        server.streams += 1

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closed:
            raise StopAsyncIteration
        try:
            return await anext(self.source)
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self):
        if self.closed:
            return
        self.closed = True
        try:
            await self.source.aclose()
        finally:
            self.server.streams -= 1


class Server(AsyncMCPServer):
    def __init__(self, topology: Topology, policy: Policy, assets: Path):
        self.topology, self.policy, self.assets = topology, policy, assets
        self.files = FileIO()
        self.auth_files = FileIO(workers=1, capacity=32)
        self.asset_cache: dict[str, bytes] = {}
        self.config_root = assets.parent.parent / "configs"
        self.adapter: SSHAdapter | None = None
        self.controller: FaultController | None = None
        self.activity = Activity()
        self.observer: Store | None = None
        self.browser_origin = "http://127.0.0.1:19000"
        self.streams = 0
        self.log_store = LogStore(topology, policy.redaction_secrets)
        super().__init__()
        self.streamable_http_max_sessions = 64
        self.streamable_http_request_timeout_seconds = 10

    def _setup_logging(self):
        self.logger = logging.getLogger("minicore")

    def get_instructions(self):
        return "IP network simulator. Operator reads measured evidence; God controls predefined lab faults. Unconfigured backends return explicit errors."

    async def authenticate_request_async(self, *, method, path, headers, peer):
        return await self.policy.authenticate_async(headers, self.auth_files)

    async def process_request_async(self, raw_message, context=None):
        # uMCP discovery is synchronous, so authenticate off-loop before dispatch.
        try:
            request = json.loads(raw_message)
        except (ValueError, TypeError):
            request = {}
        if isinstance(request, dict) and request.get("method") == "tools/list":
            headers = context.headers if context else get_request_context().headers
            try:
                principal = await self.policy.authenticate_async(headers, self.auth_files)
            except MCPAuthenticationBusy:
                return self.create_response(
                    request.get("id"), error=self.create_error(-32000, "file_io_busy")
                )
            if principal is None:
                return self.create_response(
                    request.get("id"), error=self.create_error(-32001, "authorization_denied")
                )
        try:
            return await super().process_request_async(raw_message, context=context)
        except MCPAuthenticationBusy:
            return self.create_response(
                request.get("id") if isinstance(request, dict) else None,
                error=self.create_error(-32000, "file_io_busy"),
            )

    async def close_files(self):
        await self.files.close()
        await self.auth_files.close()
        if self.controller:
            await self.controller.files.close()
        if self.adapter:
            await self.adapter.files.close()

    def authorize_request(self, principal, *, rpc_method, tool_name):
        allowed = (
            principal is not None
            and isinstance(rpc_method, (str, type(None)))
            and (
                rpc_method
                in {
                    None,
                    "initialize",
                    "notifications/initialized",
                    "notifications/cancelled",
                    "ping",
                    "tools/list",
                }
                or (rpc_method == "tools/call" and self.policy.allowed(principal, tool_name))
            )
        )
        if not allowed:
            self.logger.warning(
                json.dumps(
                    {
                        "event": "authorization_denied",
                        "at": datetime.now(timezone.utc).isoformat(),
                        "rpc_request_id": self.audit_id(get_request_context().request_id),
                        "mode": principal.roles[0] if principal else None,
                        "authorization": "denied",
                        "generation": self.topology.inventory["generation"],
                        "principal": principal.name if principal else None,
                        "tool": tool_name
                        if isinstance(tool_name, str) and tool_name in INPUTS
                        else "unknown",
                    }
                )
            )
        return allowed

    def principal(self):
        return self.policy.authenticate_cached(get_request_context().headers)

    def discover_tools(self):
        p = self.principal()
        return {
            "tools": [
                {
                    "name": name,
                    "description": (
                        "Inspect declared inventory."
                        if name == "list_nodes"
                        else "Bounded lab operation; execution backend not configured."
                    ),
                    "inputSchema": INPUTS[name],
                    "annotations": {
                        "readOnlyHint": name not in {"apply_fault", "reset_lab"},
                        "destructiveHint": name in {"apply_fault", "reset_lab"},
                        "openWorldHint": False,
                    },
                }
                for name in sorted(OPERATOR | GOD)
                if self.policy.allowed(p, name)
            ]
        }

    def validate_arguments(self, name, args):
        s = INPUTS[name]
        if (
            not isinstance(args, dict)
            or set(args) - set(s["properties"])
            or set(s["required"]) - set(args)
        ):
            raise ValueError("invalid_arguments")
        for key, value in args.items():
            rule = s["properties"][key]
            if rule["type"] == "string" and (
                not isinstance(value, str) or not value or len(value) > rule.get("maxLength", 128)
            ):
                raise ValueError("invalid_arguments")
            if rule["type"] == "integer" and (
                type(value) is not int or not rule["minimum"] <= value <= rule["maximum"]
            ):
                raise ValueError("invalid_arguments")
            if "enum" in rule and value not in rule["enum"]:
                raise ValueError("invalid_arguments")
        if name == "get_evidence":
            allowed = {
                "topology": {"kind"},
                "routing": {"kind", "prefix"},
                "observer": {"kind", "scope", "node_id", "link_id", "observation"},
                "logs": {"kind", "node_id", "limit", "cursor"},
                "configuration": {"kind", "node_id", "file"},
            }[args["kind"]]
            if set(args) - allowed or (
                args["kind"] in {"logs", "configuration"} and "node_id" not in args
            ):
                raise ValueError("invalid_arguments")
            if args["kind"] == "observer":
                observer_selector(self.topology, {k: v for k, v in args.items() if k != "kind"})
            if args["kind"] == "routing" and args.get("prefix") not in prefixes(self.topology):
                raise ValueError("invalid_prefix")
            if "file" in args and args["file"] not in {"daemons", "frr.conf", "network.json"}:
                raise ValueError("invalid_arguments")
        node = args.get("node_id")
        if node and node not in self.topology.nodes:
            raise ValueError("unknown_node")
        if "prefix" in args:
            try:
                ipaddress.IPv4Network(args["prefix"], strict=True)
            except ValueError:
                raise ValueError("invalid_prefix") from None
        if "interface" in args:
            interfaces = {
                e["interface"]
                for link in self.topology.inventory["links"]
                for e in link["endpoints"]
                if e["node"] == node
            }
            if args["interface"] not in interfaces:
                raise ValueError("unknown_interface")
        if "destination" in args:
            approved = {
                e["address"].split("/")[0]
                for link in self.topology.inventory["links"]
                for e in link["endpoints"]
            }
            if args["destination"] not in approved:
                raise ValueError("denied_destination")
        if "idempotency_key" in args and not re.fullmatch(
            "[A-Za-z0-9_-]{8,64}", args["idempotency_key"]
        ):
            raise ValueError("invalid_idempotency_key")

    @staticmethod
    def audit_id(value):
        return (
            value
            if type(value) is int
            or isinstance(value, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)
            else None
        )

    async def handle_tools_call_async(self, request_id, params):
        started = time.monotonic()
        trace = str(uuid4())
        name = params.get("name")
        args = params.get("arguments", {})
        principal = await self.policy.authenticate_async(
            get_request_context().headers, self.auth_files
        )
        record = {
            "event": "tool_completed",
            "at": datetime.now(timezone.utc).isoformat(),
            "request_id": trace,
            "rpc_request_id": self.audit_id(request_id),
            "principal": principal.name if principal else None,
            "mode": principal.roles[0] if principal else None,
            "authorization": "allowed" if self.policy.allowed(principal, name) else "denied",
            "tool": name if isinstance(name, str) and name in INPUTS else "unknown",
        }
        validated = False
        try:
            if isinstance(name, str) and name in INPUTS:
                self.validate_arguments(name, args)
                validated = True
        except ValueError:
            pass
        if validated:
            if "idempotency_key" in args:
                record["idempotency_key"] = args["idempotency_key"]
            if name == "apply_fault":
                spec = FAULT_SPECS[args["scenario_id"]]
                record.update(
                    scenario_id=args["scenario_id"],
                    target={k: spec[k] for k in ("node_id", "interface")},
                    parameters=spec["parameters"],
                )
        try:
            try:
                response = await self._handle_tools_call(request_id, params, trace)
            except OSError as exc:
                if str(exc) not in {"file_io_busy", "generation_mismatch", "redaction_unavailable"}:
                    raise
                value = self.topology.envelope(
                    str(name),
                    args.get("node_id") if isinstance(args, dict) else None,
                    error=str(exc),
                    request_id=trace,
                )
                response = self.create_response(
                    request_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(value)}],
                        "structuredContent": value,
                        "isError": True,
                    },
                )
            result = response.get("result", {}).get("structuredContent", {})
            record["error_code"] = result.get("error_code") or response.get("error", {}).get(
                "message"
            )
            record["status"] = result.get("status", "error" if "error" in response else "ok")
            if name in {"apply_fault", "reset_lab"} and isinstance(result.get("data"), dict):
                record["verified"] = result["data"].get("verified", False)
                record["controller_state"] = result["data"].get("state")
            return response
        except asyncio.CancelledError:
            record.update(status="cancelled", error_code="interrupted")
            raise
        except Exception:
            record.update(status="error", error_code="internal_error")
            raise
        finally:
            record.update(
                duration_ms=round((time.monotonic() - started) * 1000),
                generation=self.topology.inventory["generation"],
            )
            self.logger.info(json.dumps(record))

    async def _handle_tools_call(self, request_id, params, trace):
        name, args = params.get("name"), params.get("arguments", {})
        p = self.principal()
        if not isinstance(name, str) or not self.policy.allowed(p, name):
            return self.create_response(
                request_id, error=self.create_error(-32001, "authorization_denied")
            )
        try:
            self.validate_arguments(name, args)
        except ValueError as e:
            return self.create_response(
                request_id, error=self.create_error(-32602, str(e), {"request_id": trace})
            )
        if name == "get_evidence":
            if args["kind"] == "topology":
                result = self.topology.envelope(
                    "get_topology",
                    data=await self.project_topology_async("agent"),
                    request_id=trace,
                )
            elif args["kind"] == "observer":
                data = self.observer_snapshot({k: v for k, v in args.items() if k != "kind"})
                result = self.topology.envelope(
                    "get_observer", args.get("node_id"), data=data, request_id=trace
                )
            elif args["kind"] == "routing":
                result = await collect_routing(
                    self.topology, self.adapter, args["prefix"], self.activity
                )
            elif args["kind"] == "logs":
                try:
                    result = await self.log_page(
                        args["node_id"], args.get("limit", 100), args.get("cursor")
                    )
                except ValueError as exc:
                    return self.create_response(
                        request_id, error=self.create_error(-32602, str(exc))
                    )
            else:
                status, result = await self.configuration(args["node_id"], args.get("file"))
                if status != 200:
                    result = self.topology.envelope(
                        "get_declared_configuration", args["node_id"], error=result["error_code"]
                    )
            result["request_id"] = trace
            return self.create_response(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                    "structuredContent": result,
                    "isError": result["error_code"] is not None,
                },
            )
        activity_id = (
            self.activity.start(args["node_id"], self.topology.inventory["generation"])
            if name in {"get_routes", "get_interfaces", "get_neighbors", "ping"}
            else None
        )
        try:
            data, error = None, None
            if name == "list_nodes":
                data = {
                    "nodes": (await self.topology_snapshot())["nodes"],
                    "supported_operations": sorted(OPERATOR),
                    "runtime_backend": "not_configured",
                }
            elif name == "list_fault_scenarios":
                data = {
                    "scenarios": [
                        {"id": s, "available": self.controller is not None} for s in SCENARIOS
                    ]
                }
            elif (
                name in {"get_fault_state", "apply_fault", "reset_lab"}
                and self.controller is not None
            ):
                if name == "get_fault_state":
                    data = self.controller.get_state()
                else:
                    response = (
                        await self.controller.apply(
                            args["scenario_id"], args["idempotency_key"], p.name
                        )
                        if name == "apply_fault"
                        else await self.controller.reset(args["idempotency_key"], p.name)
                    )
                    data, error = response["data"], response["error_code"]
            elif (
                name in {"get_routes", "get_interfaces", "get_neighbors", "ping"}
                and self.adapter is not None
            ):
                execution = await self.adapter.execute(
                    args["node_id"],
                    {"operation": name, **{k: v for k, v in args.items() if k != "node_id"}},
                )
                data, error = execution["data"], execution["error_code"]
            else:
                error = "backend_not_configured"
        finally:
            if activity_id is not None:
                self.activity.finish(activity_id)
        result = self.topology.envelope(
            name, args.get("node_id"), data=data, error=error, request_id=trace
        )
        if (
            name in {"get_routes", "get_interfaces", "get_neighbors", "ping"}
            and self.adapter is not None
        ):
            result.update(execution)
        self.logger.info(
            json.dumps(
                {
                    "event": "tool_call",
                    "principal": p.name,
                    "mode": p.roles[0],
                    "request_id": trace,
                    "tool": name,
                    "status": result["status"],
                    "error_code": error,
                    "generation": result["generation"],
                }
            )
        )
        return self.create_response(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "structuredContent": result,
                "isError": error is not None,
            },
        )

    @staticmethod
    def response(status, payload, headers=()):
        return MCPHTTPResponse(
            status,
            json.dumps(payload).encode(),
            "application/json",
            headers + (("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")),
        )

    def read_context(self):
        topology = copy.copy(self.topology)
        topology.inventory = copy.deepcopy(self.topology.inventory)
        topology.nodes = {n["id"]: n for n in topology.inventory["nodes"]}
        return topology

    async def topology_snapshot(self):
        for _ in range(3):
            topology = self.read_context()
            result = await self.files.run(topology.snapshot)
            if topology.inventory["generation"] == self.topology.inventory["generation"]:
                self.topology._snapshot = copy.deepcopy(result)
                return result
        raise OSError("generation_mismatch")

    async def log_page(self, node, limit=100, cursor=None):
        reader = copy.copy(self.log_store)
        reader.topology = self.read_context()
        try:
            revision, reader.secrets = self.policy.redaction_context()
            result = await self.files.run(reader.page, node, limit, cursor)
            if revision != self.policy.redaction_revision:
                raise OSError("redaction_unavailable")
        except OSError as exc:
            if str(exc) != "redaction_unavailable":
                raise
            return self.topology.envelope(
                "get_logs",
                node,
                error="redaction_unavailable",
                data={"entries": [], "next_cursor": None, "revision": "unavailable"},
            )
        if reader.topology.inventory["generation"] != self.topology.inventory["generation"]:
            return self.topology.envelope(
                "get_logs",
                node,
                error="generation_mismatch",
                data={"entries": [], "next_cursor": None, "revision": "unavailable"},
            )
        return result

    async def configuration(self, node, name=None):
        topology = self.read_context()
        try:
            revision, secrets = self.policy.redaction_context()
            result = await self.files.run(baseline, topology, self.config_root, node, name, secrets)
            if revision != self.policy.redaction_revision:
                raise OSError("redaction_unavailable")
        except OSError as exc:
            if str(exc) != "redaction_unavailable":
                raise
            return 503, {"error_code": "redaction_unavailable"}
        if topology.inventory["generation"] != self.topology.inventory["generation"]:
            return 409, {"error_code": "generation_mismatch"}
        return result

    async def project_topology_async(self, view="agent"):
        return self.project_topology(view, await self.topology_snapshot())

    def project_topology(self, view="agent", snapshot=None):
        snapshot = snapshot if snapshot is not None else self.topology.snapshot()
        snapshot["view"] = view
        if view == "god":
            if self.controller is None:
                snapshot["controller"] = {
                    "state": "unavailable",
                    "error_code": "backend_not_configured",
                }
            else:
                state = self.controller.get_state()
                # Only controller public state, never stored credentials/internal journal details.
                snapshot["controller"] = {
                    key: state[key]
                    for key in (
                        "state",
                        "scenario_id",
                        "target_type",
                        "target_id",
                        "effect",
                        "node_id",
                        "interface",
                        "generation",
                        "parameters",
                        "verified",
                        "error_code",
                    )
                    if key in state
                }
        return snapshot

    async def stream_authorized(self, headers, principal):
        try:
            return (
                headers is None
                or await self.policy.authenticate_async(headers, self.auth_files) == principal
            )
        except MCPAuthenticationBusy:
            return False

    def events(self, view="agent", headers=None, principal=None):
        return AdmittedStream(self, self._events(view, headers, principal))

    async def _events(self, view, headers, principal):
        previous = None
        for _ in range(60):  # Re-authorize at least every minute; bounded per-connection lifetime.
            if not await self.stream_authorized(headers, principal):
                return
            try:
                s = await self.project_topology_async(view)
            except OSError as exc:
                if str(exc) not in {"generation_mismatch", "file_io_busy"}:
                    raise
                # No stale invalidation; reconnect starts a fresh bounded read.
                return
            if not await self.stream_authorized(headers, principal):
                return
            # Controller changes also invalidate the authorised God view.
            revision = json.dumps([s["revision"], s.get("controller")], sort_keys=True)
            if previous != revision:
                kind = "topology.snapshot" if previous is None else "topology.changed"
                yield f"id: {s['revision']}\nevent: {kind}\ndata: {json.dumps({'generation': s['generation'], 'revision': s['revision']})}\n\n".encode()
                previous = revision
            else:
                yield b": heartbeat\n\n"
            await asyncio.sleep(1)

    def log_events(self, node, headers=None, principal=None):
        return AdmittedStream(self, self._log_events(node, headers, principal))

    async def _log_events(self, node, headers, principal):
        previous = None
        for _ in range(30):
            if not await self.stream_authorized(headers, principal):
                return
            page = await self.log_page(node, limit=1)
            if not await self.stream_authorized(headers, principal):
                return
            state = (page["data"]["revision"], page["error_code"], page["generation"])
            if state != previous:
                kind = "logs.snapshot" if previous is None else "logs.changed"
                data = {
                    "node_id": node,
                    "generation": page["generation"],
                    "revision": state[0],
                    "status": page["status"],
                    "error_code": page["error_code"],
                }
                yield f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode()
                previous = state
            else:
                yield b": heartbeat\n\n"
            await asyncio.sleep(2)

    def activity_events(self, headers=None, principal=None):
        return AdmittedStream(self, self._activity_events(headers, principal))

    async def _activity_events(self, headers, principal):
        try:
            async with asyncio.timeout(60):
                while True:
                    if not await self.stream_authorized(headers, principal):
                        return
                    event = self.activity.changed
                    data = self.activity.snapshot(self.topology.inventory["generation"])
                    yield f"event: activity.snapshot\ndata: {json.dumps(data)}\n\n".encode()
                    try:
                        await asyncio.wait_for(event.wait(), timeout=2)
                    except TimeoutError:
                        pass
        except TimeoutError:
            return

    async def targeted_fault(self, args, principal):
        from .host_faults import catalogue

        if not isinstance(args, dict) or set(args) != {
            "mode",
            "target_type",
            "target_id",
            "idempotency_key",
        }:
            raise ValueError("invalid_arguments")
        if (
            args["mode"] not in {"zap", "dice"}
            or args["target_type"] not in {"node", "link"}
            or not isinstance(args["target_id"], str)
        ):
            raise ValueError("invalid_arguments")
        self.validate_arguments("reset_lab", {"idempotency_key": args["idempotency_key"]})
        specs = catalogue(self.topology.inventory)
        prefix = "zap-" if args["mode"] == "zap" else "corrupt-"
        choices = [
            name
            for name, spec in specs.items()
            if name.startswith(prefix)
            and spec["target_type"] == args["target_type"]
            and spec["target_id"] == args["target_id"]
        ]
        if not choices:
            raise ValueError("unknown_target")
        if not self.controller:
            return {"error_code": "backend_not_configured", "data": None}
        if self.controller.lock.locked():
            return self.controller.response("mutation_in_progress")
        async with self.controller.lock:
            intents = self.controller.state.setdefault("target_intents", {})
            key = args["idempotency_key"]
            old = intents.get(key)
            if old and old["request"] != args:
                return self.controller.response("idempotency_conflict")
            if old:
                if (
                    key not in self.controller.state["results"]
                    and old.get("phase", "completed") == "completed"
                ):
                    return self.controller.response("idempotency_expired")
                chosen = old["scenario"]
            else:
                if self.controller.state["state"] != "baseline":
                    return self.controller.response(
                        "fault_conflict"
                        if self.controller.state["state"] == "active"
                        else "reconciliation_required"
                    )
                if key in self.controller.state["results"]:
                    return self.controller.response("idempotency_conflict")
                chosen = secrets.choice(choices)
                intents[key] = {"request": args, "scenario": chosen, "phase": "selected"}
                while len(intents) > 128:
                    intents.pop(next(iter(intents)))
                try:
                    await self.controller.persist()
                except asyncio.CancelledError:
                    # Selected choice is durable; cancellation never rerolls it.
                    raise
                except OSError:
                    intents.pop(key, None)
                    return self.controller.response("persistence_failed")
            return await self.controller.apply_locked(chosen, key, principal)

    async def browser_fault(self, method, path, headers, body):
        p = await self.policy.authenticate_async(headers, self.auth_files)
        if not p or "god" not in p.roles:
            return self.response(403, {"error_code": "authorization_denied"})
        if method != "POST":
            return self.response(405, {"error_code": "method_not_allowed"})
        if (
            headers.get("origin") != self.browser_origin
            or headers.get("x-minicore-intent") != "fault-control"
            or headers.get("content-type") != "application/json"
        ):
            return self.response(403, {"error_code": "invalid_origin_or_intent"})
        if len(body) > 1024:
            return self.response(400, {"error_code": "invalid_arguments"})
        try:
            args = json.loads(body)
            if path == "/api/v1/faults/apply":
                result = await self.targeted_fault(args, p.name)
            elif path == "/api/v1/faults/reset":
                self.validate_arguments("reset_lab", args)
                result = (
                    await self.controller.reset(args["idempotency_key"], p.name)
                    if self.controller
                    else {"error_code": "backend_not_configured", "data": None}
                )
            else:
                return self.response(404, {"error_code": "not_found"})
        except (ValueError, TypeError):
            return self.response(400, {"error_code": "invalid_arguments"})
        self.logger.info(
            json.dumps(
                {
                    "event": "browser_fault",
                    "principal": p.name,
                    "operation": path.rsplit("/", 1)[-1],
                    "idempotency_key": args["idempotency_key"],
                    "generation": self.topology.inventory["generation"],
                    "error_code": result["error_code"],
                }
            )
        )
        return self.response(200 if not result["error_code"] else 409, result)

    def observer_snapshot(self, args):
        scope = observer_selector(self.topology, args)
        store = self.observer
        if store is None:
            store = Store(self.topology.inventory["lab_id"], self.topology.inventory["generation"])
        if store.generation != self.topology.inventory["generation"]:
            store.reset(self.topology.inventory["generation"])
        if args["scope"] == "link":
            return link_snapshot(store, self.topology, args["link_id"], args["observation"])
        return store.snapshot(scope)

    def observer_events(self, headers, principal):
        return AdmittedStream(self, self._observer_events(headers, principal))

    async def _observer_events(self, headers, principal):
        previous = None
        for _ in range(60):
            if not await self.stream_authorized(headers, principal):
                return
            store = self.observer
            if store:
                if store.generation != self.topology.inventory["generation"]:
                    store.reset(self.topology.inventory["generation"])
                store.sweep()
            value = {
                "observer_epoch": store.epoch if store else None,
                "generation": self.topology.inventory["generation"],
                "revision": store.revision if store else 0,
            }
            text = json.dumps(value)
            yield (
                f"event: observer.changed\ndata: {text}\n\n"
                if text != previous
                else ": heartbeat\n\n"
            ).encode()
            previous = text
            await asyncio.sleep(1)

    async def handle_http_request_async(self, *, method, path, headers, body, peer):
        try:
            return await self._handle_http(
                method=method, path=path, headers=headers, body=body, peer=peer
            )
        except OSError as exc:
            if str(exc) in {"file_io_busy", "generation_mismatch"}:
                status = 409 if str(exc) == "generation_mismatch" else 503
                return self.response(status, {"error_code": str(exc)})
            raise

    async def _handle_http(self, *, method, path, headers, body, peer):
        target = urlsplit(path)
        path = target.path
        if path in {"/api/v1/faults/apply", "/api/v1/faults/reset"}:
            if target.query:
                return self.response(400, {"error_code": "invalid_arguments"})
            return await self.browser_fault(method, path, headers, body)
        if method != "GET":
            return self.response(405, {"error_code": "method_not_allowed"}, (("Allow", "GET"),))
        if path == "/healthz":
            return self.response(
                200, {"status": "ready", "scope": "management", "runtime_backend": "not_configured"}
            )
        p = await self.policy.authenticate_async(headers, self.auth_files)
        if p is None:
            return self.response(
                401,
                {"error_code": "authentication_required"},
                (("WWW-Authenticate", 'Basic realm="Minicore", charset="UTF-8"'),),
            )
        if path in {"/api/v1/observer", "/api/v1/observer/events"}:
            if path.endswith("/events"):
                if target.query:
                    return self.response(400, {"error_code": "invalid_arguments"})
                if self.streams >= 16:
                    return self.response(503, {"error_code": "stream_limit"})
                return MCPHTTPResponse(
                    200,
                    content_type="text/event-stream",
                    headers=(("Cache-Control", "no-store"),),
                    stream=self.observer_events(headers, p),
                )
            try:
                query = parse_qs(
                    target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=3
                )
                if any(len(v) != 1 for v in query.values()) or "kind" not in query:
                    raise ValueError()
                args = {k: v[0] for k, v in query.items()}
                args["observation"] = args.pop("kind")
                result = self.observer_snapshot(args)
            except ValueError:
                return self.response(400, {"error_code": "invalid_arguments"})
            return self.response(200, result)
        if path in {"/api/v1/topology", "/api/v1/events"}:
            try:
                query = parse_qs(
                    target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=1
                )
                if set(query) - {"view"} or any(len(v) != 1 for v in query.values()):
                    raise ValueError()
                view = query.get("view", ["agent"])[0]
                if view not in {"agent", "god"}:
                    raise ValueError()
            except ValueError:
                return self.response(400, {"error_code": "invalid_arguments"})
            if view == "god" and "god" not in p.roles:
                return self.response(403, {"error_code": "authorization_denied"})
            if path == "/api/v1/topology":
                snapshot = await self.project_topology_async(view)
                if not await self.stream_authorized(headers, p):
                    return self.response(401, {"error_code": "authentication_required"})
                return self.response(200, snapshot)
            if self.streams >= 16:
                return self.response(503, {"error_code": "stream_limit"})
            return MCPHTTPResponse(
                200,
                content_type="text/event-stream",
                headers=(("Cache-Control", "no-store"), ("X-Accel-Buffering", "no")),
                stream=self.events(view, headers, p),
            )
        if path == "/api/v1/view" and not target.query:
            return self.response(
                200,
                {
                    "can_god": "god" in p.roles,
                    "fault_control": bool(
                        self.controller
                        and "zap-node-p1" in self.controller.scenarios
                        and "god" in p.roles
                    ),
                    "default_view": "agent",
                    "evidence_contract": "operator-v2",
                },
            )
        inspector_match = re.fullmatch(r"/api/v1/nodes/([a-z0-9]+)/observations", path)
        if inspector_match:
            node = inspector_match.group(1)
            if node not in self.topology.nodes:
                return self.response(404, {"error_code": "unknown_node"})
            if target.query:
                return self.response(400, {"error_code": "invalid_arguments"})
            from .observations import collect

            return self.response(200, await collect(self.topology, self.adapter, node))
        log_match = re.fullmatch(r"/api/v1/nodes/([a-z0-9]+)/logs(/events)?", path)
        if log_match:
            node, event_stream = log_match.groups()
            if node not in self.topology.nodes:
                return self.response(404, {"error_code": "unknown_node"})
            try:
                query = parse_qs(
                    target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=3
                )
                if (
                    set(query) - {"limit", "cursor"}
                    or any(len(v) != 1 for v in query.values())
                    or (event_stream and query)
                ):
                    raise ValueError("invalid_arguments")
                limit_text = query.get("limit", ["100"])[0]
                if not re.fullmatch(r"[0-9]{1,3}", limit_text):
                    raise ValueError("invalid_limit")
                result = await self.log_page(node, int(limit_text), query.get("cursor", [None])[0])
            except ValueError as exc:
                code = (
                    str(exc)
                    if str(exc)
                    in {"invalid_limit", "invalid_cursor", "cursor_expired", "invalid_arguments"}
                    else "invalid_arguments"
                )
                return self.response(409 if code == "cursor_expired" else 400, {"error_code": code})
            if event_stream:
                if self.streams >= 16:
                    return self.response(503, {"error_code": "stream_limit"})
                return MCPHTTPResponse(
                    200,
                    content_type="text/event-stream",
                    headers=(("Cache-Control", "no-store"), ("X-Accel-Buffering", "no")),
                    stream=self.log_events(node, headers, p),
                )
            return self.response(200 if result["status"] == "ok" else 503, result)
        if path == "/api/v1/routing":
            try:
                query = parse_qs(
                    target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=1
                )
                if set(query) != {"prefix"} or len(query["prefix"]) != 1:
                    raise ValueError()
                result = await collect_routing(self.topology, self.adapter, query["prefix"][0])
            except ValueError:
                return self.response(400, {"error_code": "invalid_arguments"})
            return self.response(200, result)
        route_match = re.fullmatch(r"/api/v1/nodes/([a-z0-9]+)/routes", path)
        if route_match:
            node = route_match.group(1)
            if node not in self.topology.nodes:
                return self.response(404, {"error_code": "unknown_node"})
            try:
                query = parse_qs(
                    target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=1
                )
                if set(query) - {"prefix"} or any(len(v) != 1 for v in query.values()):
                    raise ValueError()
                args = {
                    "node_id": node,
                    **({"prefix": query["prefix"][0]} if "prefix" in query else {}),
                }
                self.validate_arguments("get_routes", args)
            except ValueError:
                return self.response(400, {"error_code": "invalid_arguments"})
            result = self.topology.envelope("get_routes", node, error="backend_not_configured")
            if self.adapter:
                result.update(
                    await self.adapter.execute(
                        node,
                        {
                            "operation": "get_routes",
                            **{k: v for k, v in args.items() if k != "node_id"},
                        },
                    )
                )
            return self.response(200 if result["status"] == "ok" else 503, result)
        if target.query:
            return self.response(400, {"error_code": "invalid_arguments"})
        config_match = re.fullmatch(r"/api/v1/nodes/([a-z0-9]+)/config(?:/([a-z.]+))?", path)
        if config_match:
            node, name = config_match.groups()
            status, payload = await self.configuration(node, name)
            return self.response(status, payload)
        if path == "/api/v1/activity":
            return self.response(200, self.activity.snapshot(self.topology.inventory["generation"]))
        if path == "/api/v1/activity/events":
            if self.streams >= 16:
                return self.response(503, {"error_code": "stream_limit"})
            return MCPHTTPResponse(
                200,
                content_type="text/event-stream",
                headers=(("Cache-Control", "no-store"), ("X-Accel-Buffering", "no")),
                stream=self.activity_events(headers, p),
            )
        match = re.fullmatch("/api/v1/nodes/([a-z0-9]+)", path)
        if match:
            node = match.group(1)
            if node not in self.topology.nodes:
                return self.response(404, {"error_code": "unknown_node"})
            return self.response(
                200,
                self.topology.envelope(
                    "get_node",
                    node,
                    data=next(
                        n for n in (await self.topology_snapshot())["nodes"] if n["id"] == node
                    ),
                ),
            )
        # Exact asset allow-list. No arbitrary path or source map serving.
        filenames = {
            "/": "index.html",
            "/assets/main.js": "main.js",
            "/assets/styles.css": "styles.css",
        }
        if path in filenames:
            file = self.assets / filenames[path]
            try:
                if path not in self.asset_cache:
                    self.asset_cache[path] = await self.files.run(file.read_bytes)
            except FileNotFoundError:
                return self.response(404, {"error_code": "not_found"})
            else:
                mime = {
                    "html": "text/html; charset=utf-8",
                    "js": "text/javascript",
                    "css": "text/css",
                }[file.suffix[1:]]
                return MCPHTTPResponse(
                    200,
                    self.asset_cache[path],
                    mime,
                    (
                        ("Cache-Control", "no-cache"),
                        ("X-Content-Type-Options", "nosniff"),
                        (
                            "Content-Security-Policy",
                            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                        ),
                    ),
                )
        return self.response(404, {"error_code": "not_found"})
