#!/usr/bin/env python3
"""Async memory-only host counter service. No traffic files, no packet capture in this slice."""

import asyncio
import json
import os
from pathlib import Path
import resource
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-service/src"))
from minicore_mcp.observer_service import CounterService  # noqa: E402


async def run(inventory):
    path = ROOT / "runtime/observer-socket/counters.sock"
    service = CounterService(inventory, path)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await service.start()
        await stop.wait()
    finally:
        await service.close()


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    inventory = json.loads((ROOT / "inventory/topology.json").read_text())
    path = ROOT / "runtime/observer-socket/counters.sock"
    if path.exists():
        path.unlink()  # owned singleton systemd lifecycle only
    asyncio.run(run(inventory))
