"""Narrow fixed fault transport and measured baseline verification."""

import asyncio
import time

from .faults import SCENARIOS
from .ssh_adapter import SSHAdapter


class FaultExecutor:
    def __init__(self, topology, diagnostic, directory):
        self.topology = topology
        self.diagnostic = diagnostic
        self.fault = SSHAdapter(topology, directory, fault=True)

    async def mutate(self, scenario, action):
        spec = SCENARIOS[scenario]
        result = await self.fault.execute(
            spec["node_id"], {"operation": "fault", "scenario": scenario, "action": action}
        )
        return (
            result["data"]
            if result["status"] == "ok"
            else {"ok": False, "verified": False, "error_code": result["error_code"]}
        )

    async def verify_baseline(self):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                results = await asyncio.gather(
                    *(
                        self.diagnostic.execute(
                            node, {"operation": "get_neighbors", "protocol": "bgp"}
                        )
                        for node in ["p1", "p2", "pe1", "pe2", "ce1", "ce2"]
                    )
                )
                counts = [3, 3, 4, 4, 1, 1]
                good = all(
                    r["status"] == "ok"
                    and len(r["data"].get("ipv4Unicast", {}).get("peers", {})) == count
                    and all(
                        p.get("state") == "Established"
                        for p in r["data"]["ipv4Unicast"]["peers"].values()
                    )
                    for r, count in zip(results, counts, strict=False)
                )
                ospf = await asyncio.gather(
                    *(
                        self.diagnostic.execute(
                            node, {"operation": "get_neighbors", "protocol": "ospf"}
                        )
                        for node in ["p1", "p2", "pe1", "pe2"]
                    )
                )
                full = sum(
                    1
                    for r in ospf
                    if r["status"] == "ok"
                    for group in r["data"].get("neighbors", r["data"]).values()
                    for p in group
                    if str(p.get("nbrState", "")).startswith("Full")
                )
                if good and full == 10:
                    probes = await asyncio.gather(
                        self.diagnostic.execute(
                            "ce1",
                            {
                                "operation": "ping",
                                "destination": "10.200.9.2",
                                "source_interface": "to-host1",
                                "count": 2,
                            },
                        ),
                        self.diagnostic.execute(
                            "ce2",
                            {
                                "operation": "ping",
                                "destination": "10.200.8.2",
                                "source_interface": "to-host2",
                                "count": 2,
                            },
                        ),
                    )
                    if all(r["status"] == "ok" and r["data"]["received"] == 2 for r in probes):
                        return True
            except (ValueError, KeyError, TypeError):
                pass
            await asyncio.sleep(1)
        return False
