import asyncio
import logging
import os
from pathlib import Path

from .model import Topology
from .policy import Policy
from .server import Server
from .ssh_adapter import SSHAdapter


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(os.environ.get("MINICORE_ROOT", "/app"))
    topology = Topology(
        root / "inventory/topology.json",
        Path(os.environ.get("MINICORE_OBSERVATIONS", "/runtime/observations.json")),
    )
    policy = Policy(
        os.environ.get("MINICORE_EXPOSURE_PROFILE", "authenticated"),
        Path(os.environ.get("MINICORE_TOKEN_FILE", "/run/secrets/mcp-tokens.json")),
    )
    server = Server(topology, policy, root / "web-ui/dist")
    if os.environ.get("MINICORE_SSH_DIR"):
        server.adapter = SSHAdapter(topology, Path(os.environ["MINICORE_SSH_DIR"]))
    if policy.profile == "private":
        logging.warning(
            "Private lab profile: reachable anonymous callers have Operator access; no individual identity."
        )
    asyncio.run(
        server.run_streamable_http_async(
            host=os.environ.get("MINICORE_HOST", "0.0.0.0"),
            port=int(os.environ.get("MINICORE_PORT", "9000")),
            endpoint="/mcp",
            allowed_origins=os.environ.get(
                "MINICORE_ALLOWED_ORIGINS", "http://127.0.0.1:19000"
            ).split(","),
            max_request_bytes=2 * 1024 * 1024,
        )
    )


if __name__ == "__main__":
    main()
