"""One uMCP listener: role-filtered MCP and read-only HTTP/SSE assets."""

import asyncio
import ipaddress
import json
import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from aioumcp import AsyncMCPServer
from umcp_shared import MCPHTTPResponse, get_request_context

from .activity import Activity
from .configuration import baseline
from .faults import FaultController
from .logs import LogStore
from .model import Topology
from .policy import GOD, OPERATOR, Policy
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
            "kind": {"type": "string", "enum": ["topology", "logs", "configuration"]},
            "node_id": STRING,
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


class Server(AsyncMCPServer):
    def __init__(self, topology: Topology, policy: Policy, assets: Path):
        self.topology, self.policy, self.assets = topology, policy, assets
        self.config_root = assets.parent.parent / "configs"
        self.adapter: SSHAdapter | None = None
        self.controller: FaultController | None = None
        self.activity = Activity()
        self.streams = 0
        self.log_store = LogStore(topology, policy.credentials.values())
        super().__init__()
        self.streamable_http_max_sessions = 64
        self.streamable_http_request_timeout_seconds = 10

    def _setup_logging(self):
        self.logger = logging.getLogger("minicore")

    def get_instructions(self):
        return "IP network simulator. Operator reads measured evidence; God controls predefined lab faults. Unconfigured backends return explicit errors."

    def authenticate_request(self, *, method, path, headers, peer):
        return self.policy.authenticate(headers)

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
                        "principal": principal.name if principal else None,
                        "tool": tool_name
                        if isinstance(tool_name, str) and tool_name in INPUTS
                        else "unknown",
                    }
                )
            )
        return allowed

    def principal(self):
        return self.policy.authenticate(get_request_context().headers)

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
                "logs": {"kind", "node_id", "limit", "cursor"},
                "configuration": {"kind", "node_id", "file"},
            }[args["kind"]]
            if set(args) - allowed or (args["kind"] != "topology" and "node_id" not in args):
                raise ValueError("invalid_arguments")
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

    async def handle_tools_call_async(self, request_id, params):
        name, args = params.get("name"), params.get("arguments", {})
        p = self.principal()
        trace = str(uuid4())
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
                    "get_topology", data=self.project_topology("agent"), request_id=trace
                )
            elif args["kind"] == "logs":
                try:
                    result = self.log_store.page(
                        args["node_id"], args.get("limit", 100), args.get("cursor")
                    )
                except ValueError as exc:
                    return self.create_response(
                        request_id, error=self.create_error(-32602, str(exc))
                    )
            else:
                status, result = baseline(
                    self.topology,
                    self.config_root,
                    args["node_id"],
                    args.get("file"),
                    self.policy.credentials.values(),
                )
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
                    "nodes": self.topology.snapshot()["nodes"],
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

    def project_topology(self, view="agent"):
        snapshot = self.topology.snapshot()
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

    async def events(self, view="agent"):
        previous = None
        self.streams += 1
        try:
            for _ in range(
                60
            ):  # Re-authorize at least every minute; bounded per-connection lifetime.
                s = self.project_topology(view)
                # Controller changes also invalidate the authorised God view.
                revision = json.dumps([s["revision"], s.get("controller")], sort_keys=True)
                if previous != revision:
                    kind = "topology.snapshot" if previous is None else "topology.changed"
                    yield f"id: {s['revision']}\nevent: {kind}\ndata: {json.dumps({'generation': s['generation'], 'revision': s['revision']})}\n\n".encode()
                    previous = revision
                else:
                    yield b": heartbeat\n\n"
                await asyncio.sleep(1)
        finally:
            self.streams -= 1

    async def log_events(self, node):
        previous = None
        self.streams += 1
        try:
            for _ in range(30):
                page = self.log_store.page(node, limit=1)
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
        finally:
            self.streams -= 1

    async def activity_events(self):
        self.streams += 1
        try:
            async with asyncio.timeout(60):
                while True:
                    event = self.activity.changed
                    data = self.activity.snapshot(self.topology.inventory["generation"])
                    yield f"event: activity.snapshot\ndata: {json.dumps(data)}\n\n".encode()
                    try:
                        await asyncio.wait_for(event.wait(), timeout=2)
                    except TimeoutError:
                        pass
        except TimeoutError:
            return
        finally:
            self.streams -= 1

    async def handle_http_request_async(self, *, method, path, headers, body, peer):
        target = urlsplit(path)
        path = target.path
        if method != "GET":
            return self.response(405, {"error_code": "method_not_allowed"}, (("Allow", "GET"),))
        if path == "/healthz":
            return self.response(
                200, {"status": "ready", "scope": "management", "runtime_backend": "not_configured"}
            )
        p = self.policy.authenticate(headers)
        if p is None:
            return self.response(
                401,
                {"error_code": "authentication_required"},
                (("WWW-Authenticate", 'Basic realm="Minicore", charset="UTF-8"'),),
            )
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
                return self.response(200, self.project_topology(view))
            if self.streams >= 16:
                return self.response(503, {"error_code": "stream_limit"})
            return MCPHTTPResponse(
                200,
                content_type="text/event-stream",
                headers=(("Cache-Control", "no-store"), ("X-Accel-Buffering", "no")),
                stream=self.events(view),
            )
        if path == "/api/v1/view" and not target.query:
            return self.response(
                200,
                {
                    "can_god": "god" in p.roles,
                    "default_view": "agent",
                    "evidence_contract": "operator-v2",
                },
            )
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
                result = self.log_store.page(node, int(limit_text), query.get("cursor", [None])[0])
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
                    stream=self.log_events(node),
                )
            return self.response(200 if result["status"] == "ok" else 503, result)
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
            status, payload = baseline(
                self.topology, self.config_root, node, name, self.policy.credentials.values()
            )
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
                stream=self.activity_events(),
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
                    data=next(n for n in self.topology.snapshot()["nodes"] if n["id"] == node),
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
            if file.exists():
                mime = {
                    "html": "text/html; charset=utf-8",
                    "js": "text/javascript",
                    "css": "text/css",
                }[file.suffix[1:]]
                return MCPHTTPResponse(
                    200,
                    file.read_bytes(),
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
