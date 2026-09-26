"""Two server-derived roles. Bounded credential reload, fail closed on rotation errors."""

import asyncio
import base64
import copy
import hmac
import json
from pathlib import Path

from umcp_shared import MCPAuthenticationBusy, MCPPrincipal

from .file_io import FileIO

OPERATOR = {"list_nodes", "get_interfaces", "get_routes", "get_neighbors", "ping", "get_evidence"}
GOD = {"list_fault_scenarios", "apply_fault", "get_fault_state", "reset_lab"}


class Policy:
    def __init__(self, profile: str, token_file: Path):
        if profile not in {"private", "authenticated"}:
            raise ValueError("Unknown exposure profile")
        self._reload_lock = asyncio.Lock()
        self._auth_pending = 0
        self.profile = profile
        self.token_file = token_file
        self.required_file = token_file.exists() or profile == "authenticated"
        self.invalid = False
        self.credentials: dict[str, str] = {}
        # Redaction history is immutable, process-local and independent of auth.
        # Never evict a secret that could still occur in retained evidence.
        self.redaction_secrets: tuple[str, ...] = ()
        self.redaction_blocked = False
        self.redaction_revision = 0
        self._fingerprint: tuple[int, int, int] | None = None
        self.reload()
        if self.invalid:
            raise ValueError("Invalid credential configuration")

    def reload(self):
        try:
            stat = self.token_file.stat()
            fingerprint = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            if fingerprint == self._fingerprint:
                return
            if stat.st_size > 16384:
                raise ValueError("Credential file too large")
            with self.token_file.open("rb") as handle:
                raw = handle.read(16385)
            if len(raw) > 16384:
                raise ValueError("Credential file too large")
            credentials = json.loads(raw)
            self.validate(credentials)
            self.remember_secrets(credentials.values())
            # Mutate in place so existing redaction views see the new credentials.
            self.credentials.clear()
            self.credentials.update(credentials)
            self.required_file = True
            self._fingerprint = fingerprint
            self.invalid = False
        except FileNotFoundError:
            self.invalid = self.required_file
            self._fingerprint = None
            if self.invalid:
                self.credentials.clear()
        except (OSError, ValueError, TypeError):
            self.invalid = True
            self._fingerprint = None
            self.credentials.clear()

    def remember_secrets(self, values):
        if self.redaction_blocked:
            return
        combined = tuple(dict.fromkeys((*self.redaction_secrets, *values)))
        if len(combined) > 128 or sum(len(s.encode()) for s in combined) > 64 * 1024:
            self.redaction_blocked = True
            self.redaction_revision += 1
        elif combined != self.redaction_secrets:
            self.redaction_secrets = combined
            self.redaction_revision += 1

    def redaction_context(self):
        if self.redaction_blocked:
            raise OSError("redaction_unavailable")
        return self.redaction_revision, self.redaction_secrets

    def validate(self, credentials):
        if not isinstance(credentials, dict) or set(credentials) - {"operator", "god"}:
            raise ValueError("Invalid credential roles")
        values = list(credentials.values())
        if any(not isinstance(x, str) or len(x) < 32 for x in values) or len(values) != len(
            set(values)
        ):
            raise ValueError("Credentials must be distinct strings of at least 32 characters")
        if self.profile == "authenticated" and "operator" not in credentials:
            raise ValueError("Authenticated deployment requires Operator credential")

    async def authenticate_async(self, headers, files):
        if self._auth_pending >= 32:
            raise MCPAuthenticationBusy("file_io_busy")
        self._auth_pending += 1
        try:
            async with self._reload_lock:
                clone = copy.copy(self)
                clone.credentials = dict(self.credentials)
                reload = asyncio.create_task(files.run(clone.reload))
                try:
                    # Reload is service state, independent of the caller's lifetime.
                    # Drain it under the lock and publish even if that caller cancels.
                    await FileIO.drain(reload)
                except OSError as exc:
                    if str(exc) == "file_io_busy":
                        raise MCPAuthenticationBusy("file_io_busy") from None
                    return None
                finally:
                    if reload.done() and not reload.cancelled() and reload.exception() is None:
                        self.credentials.clear()
                        self.credentials.update(clone.credentials)
                        self.required_file = clone.required_file
                        self._fingerprint = clone._fingerprint
                        self.invalid = clone.invalid
                        self.redaction_secrets = clone.redaction_secrets
                        self.redaction_blocked = clone.redaction_blocked
                        self.redaction_revision = clone.redaction_revision
                return self.authenticate_cached(headers)
        finally:
            self._auth_pending -= 1

    def authenticate(self, headers):
        self.reload()
        return self.authenticate_cached(headers)

    def authenticate_cached(self, headers):
        if self.invalid:
            return None
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
                basic_expected = self.credentials.get(user) if user in {"operator", "god"} else None
                if basic_expected and hmac.compare_digest(token.encode(), basic_expected.encode()):
                    return MCPPrincipal(name=user, roles=(user,))
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
