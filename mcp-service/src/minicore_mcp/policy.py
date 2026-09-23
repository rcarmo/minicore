"""Two roles only. Bearer for MCP, Operator-only Basic for browser access."""

import base64
import hmac
import json
from pathlib import Path

from umcp_shared import MCPPrincipal

OPERATOR = {"list_nodes", "get_interfaces", "get_routes", "get_neighbors", "ping"}
GOD = {"list_fault_scenarios", "apply_fault", "get_fault_state", "reset_lab"}


class Policy:
    def __init__(self, profile: str, token_file: Path):
        if profile not in {"private", "authenticated"}:
            raise ValueError("Unknown exposure profile")
        self.profile = profile
        self.credentials = json.loads(token_file.read_text()) if token_file.exists() else {}
        if not isinstance(self.credentials, dict) or set(self.credentials) - {"operator", "god"}:
            raise ValueError("Invalid credential roles")
        values = list(self.credentials.values())
        if any(not isinstance(x, str) or len(x) < 32 for x in values) or len(values) != len(
            set(values)
        ):
            raise ValueError("Credentials must be distinct strings of at least 32 characters")
        if profile == "authenticated" and "operator" not in self.credentials:
            raise ValueError("Authenticated deployment requires Operator credential")

    def authenticate(self, headers):
        auth = headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            for mode, expected in self.credentials.items():
                if hmac.compare_digest(token.encode(), expected.encode()):
                    return MCPPrincipal(name=mode, roles=(mode,))
            return None
        if auth.startswith("Basic "):
            try:
                user, token = base64.b64decode(auth[6:], validate=True).decode().split(":", 1)
                expected = self.credentials.get("operator")
                if (
                    user == "operator"
                    and expected
                    and hmac.compare_digest(token.encode(), expected.encode())
                ):
                    return MCPPrincipal(name="operator", roles=("operator",))
            except (ValueError, UnicodeError):
                pass
            return None
        if not auth and self.profile == "private":
            return MCPPrincipal(name="anonymous", roles=("operator",))
        return None

    @staticmethod
    def allowed(principal, tool):
        return (
            principal is not None
            and isinstance(tool, str)
            and (tool in OPERATOR or ("god" in principal.roles and tool in GOD))
        )
