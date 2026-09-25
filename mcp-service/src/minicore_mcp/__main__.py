import asyncio
import logging
import os
from pathlib import Path

from .fault_executor import FaultExecutor
from .faults import FaultController
from .host_faults import CombinedExecutor, HostAdapter, catalogue
from .model import Topology
from .observer_service import ObserverRuntime
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
    if os.environ.get("MINICORE_FAULT_DIR") and server.adapter:
        executor: FaultExecutor | CombinedExecutor = FaultExecutor(
            topology, server.adapter, Path(os.environ["MINICORE_FAULT_DIR"])
        )
        host_socket = os.environ.get("MINICORE_HOST_FAULT_SOCKET")
        if host_socket:
            executor = CombinedExecutor(
                executor, HostAdapter(Path(host_socket)), topology.inventory
            )
        server.controller = FaultController(
            topology,
            executor,
            Path(os.environ.get("MINICORE_CONTROL_DIR", "/control")),
            catalogue=catalogue(topology.inventory) if host_socket else None,
        )
    if policy.profile == "private":
        logging.warning(
            "Private lab profile: reachable anonymous callers have Operator access; no individual identity."
        )
    server.browser_origin = os.environ.get("MINICORE_BROWSER_ORIGIN", "http://127.0.0.1:19000")

    async def run():
        observer = None
        path = os.environ.get("MINICORE_OBSERVER_SOCKET")
        if path:
            observer = ObserverRuntime(topology, server.adapter, Path(path))
            server.observer = observer.store
            await observer.start()
        try:
            await server.run_streamable_http_async(
                host=os.environ.get("MINICORE_HOST", "0.0.0.0"),
                port=int(os.environ.get("MINICORE_PORT", "9000")),
                endpoint="/mcp",
                allowed_origins=os.environ.get(
                    "MINICORE_ALLOWED_ORIGINS", "http://127.0.0.1:19000"
                ).split(","),
                max_request_bytes=2 * 1024 * 1024,
            )
        finally:
            if observer:
                await observer.close()
            await server.close_files()

    asyncio.run(run())


if __name__ == "__main__":
    main()
