"""One uMCP listener: role-filtered MCP and read-only HTTP/SSE assets."""

import asyncio
import ipaddress
import json
import logging
import re
from pathlib import Path
from uuid import uuid4

from aioumcp import AsyncMCPServer
from umcp_shared import MCPHTTPResponse, get_request_context

from .model import Topology
from .policy import GOD, OPERATOR, Policy

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
        self.streams = 0
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
        allowed = principal is not None and (
            rpc_method in {None, "initialize", "notifications/initialized", "ping", "tools/list"}
            or (rpc_method == "tools/call" and self.policy.allowed(principal, tool_name))
        )
        if not allowed:
            self.logger.warning(
                json.dumps(
                    {
                        "event": "authorization_denied",
                        "principal": principal.name if principal else None,
                        "tool": tool_name if tool_name in INPUTS else "unknown",
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
                not isinstance(value, str) or not value or len(value) > 128
            ):
                raise ValueError("invalid_arguments")
            if rule["type"] == "integer" and (
                type(value) is not int or not rule["minimum"] <= value <= rule["maximum"]
            ):
                raise ValueError("invalid_arguments")
            if "enum" in rule and value not in rule["enum"]:
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
        data, error = None, None
        if name == "list_nodes":
            data = {
                "nodes": self.topology.snapshot()["nodes"],
                "supported_operations": sorted(OPERATOR),
                "runtime_backend": "not_configured",
            }
        elif name == "list_fault_scenarios":
            data = {"scenarios": [{"id": s, "available": False} for s in SCENARIOS]}
        else:
            error = "backend_not_configured"
        result = self.topology.envelope(
            name, args.get("node_id"), data=data, error=error, request_id=trace
        )
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

    async def events(self):
        previous = None
        self.streams += 1
        try:
            for _ in range(
                60
            ):  # Re-authorize at least every minute; bounded per-connection lifetime.
                s = self.topology.snapshot()
                if previous != s["revision"]:
                    kind = "topology.snapshot" if previous is None else "topology.changed"
                    yield f"id: {s['revision']}\nevent: {kind}\ndata: {json.dumps({'generation': s['generation'], 'revision': s['revision']})}\n\n".encode()
                    previous = s["revision"]
                else:
                    yield b": heartbeat\n\n"
                await asyncio.sleep(1)
        finally:
            self.streams -= 1

    async def handle_http_request_async(self, *, method, path, headers, body, peer):
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
        if path == "/api/v1/topology":
            return self.response(200, self.topology.snapshot())
        if path == "/api/v1/events":
            if self.streams >= 16:
                return self.response(503, {"error_code": "stream_limit"})
            return MCPHTTPResponse(
                200,
                content_type="text/event-stream",
                headers=(("Cache-Control", "no-store"), ("X-Accel-Buffering", "no")),
                stream=self.events(),
            )
        match = re.fullmatch("/api/v1/nodes/([a-z0-9]+)/?(logs)?", path)
        if match:
            node, logs = match.groups()
            if node not in self.topology.nodes:
                return self.response(404, {"error_code": "unknown_node"})
            if logs:
                return self.response(
                    503,
                    self.topology.envelope(
                        "get_logs",
                        node,
                        data={"entries": [], "next_cursor": None},
                        error="backend_not_configured",
                    ),
                )
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
