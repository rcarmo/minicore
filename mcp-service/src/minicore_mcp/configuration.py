"""Known-node baseline file tree, never a filesystem browser or running-config claim."""

import hashlib
import json
import re
from pathlib import Path

from .logs import redact

MAX_FILE = 32 * 1024


def baseline(topology, root: Path, node: str, name: str | None, secrets=()):
    if node not in topology.nodes:
        return 404, {"error_code": "unknown_node"}
    names = (
        ["daemons", "frr.conf"] if topology.nodes[node]["kind"] == "router" else ["network.json"]
    )
    if name is not None and name not in names:
        return 404, {"error_code": "unknown_configuration_file"}
    data = {"node_id": node, "source": "declared_baseline", "running_verified": False}
    if name is None:
        data["files"] = [{"name": item} for item in names]
    else:
        path = root / node / name
        try:
            if root.is_symlink() or path.parent.is_symlink() or path.is_symlink():
                raise OSError("Symlink is not a baseline file")
            with path.open("rb") as handle:
                raw = handle.read(MAX_FILE + 1)
            if len(raw) > MAX_FILE:
                return 413, {"error_code": "configuration_too_large"}
            text = raw.decode("utf-8")
            # Hide entire sensitive FRR lines: passwords include positional CLI syntax.
            text = "\n".join(
                "[REDACTED configuration directive]"
                if re.search(r"\b(password|secret|community|key-string|private-key)\b", line, re.I)
                else line
                for line in text.split("\n")
            )
            text = re.sub(
                r"-----BEGIN .*?PRIVATE KEY-----[\s\S]*?(?:-----END .*?PRIVATE KEY-----|\Z)",
                "[REDACTED private key]",
                text,
            )
            text = redact(text, secrets)
            data.update(
                {
                    "name": name,
                    "content": text,
                    "revision": hashlib.sha256(text.encode()).hexdigest(),
                    "redacted": text != raw.decode("utf-8"),
                    "bytes": len(text.encode()),
                }
            )
        except (OSError, UnicodeError):
            return 503, {"error_code": "configuration_unavailable"}
    result = topology.envelope("get_declared_configuration", node, data=data)
    # An expanding JSON encoding must remain bounded too.
    if len(json.dumps(result).encode()) > 64 * 1024:
        return 413, {"error_code": "configuration_too_large"}
    return 200, result
