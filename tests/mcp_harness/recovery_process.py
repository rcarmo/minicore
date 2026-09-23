"""Runs inside management as its non-root UID; disposable journal, real SSH executor.

Only the test wrapper injects interruption after the actual mutation returns.
Production controller/dispatcher code has no fault-injection hook.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from minicore_mcp.fault_executor import FaultExecutor
from minicore_mcp.faults import FaultController
from minicore_mcp.model import Topology
from minicore_mcp.ssh_adapter import SSHAdapter


async def main():
    action, directory, scenario = sys.argv[1:]
    topology = Topology(Path("/app/inventory/topology.json"), Path("/runtime/observations.json"))
    diagnostic = SSHAdapter(topology, Path("/run/ssh-client"))
    real = FaultExecutor(topology, diagnostic, Path("/run/fault-client"))

    class Interrupted:
        async def verify_baseline(self):
            return await real.verify_baseline()

        async def mutate(self, name, operation):
            value = await real.mutate(name, operation)
            assert value["ok"] and value["verified"], value
            if action == "crash":
                os._exit(77)
            raise asyncio.CancelledError()

    controller = FaultController(
        topology, real if action == "recover" else Interrupted(), Path(directory)
    )
    if action == "recover":
        before = controller.get_state()
        assert before["state"] == "reconciliation_required" and before["verified"] is False, before
        denied = await controller.apply("data-path-degradation", "new-apply-key", "god")
        assert denied["error_code"] == "reconciliation_required", denied
        result = await controller.reset("explicit-reset-key", "god")
        assert (
            result["error_code"] is None
            and result["data"]["verified"]
            and result["data"]["state"] == "baseline"
        ), result
        assert result["data"]["generation"] == before["generation"] + 1, result
        replay = await controller.reset("explicit-reset-key", "god")
        assert replay == result
        print(json.dumps({"before": before, "after": result["data"], "replay_equal": True}))
    else:
        try:
            await controller.apply(scenario, "ambiguous-apply-key", "god")
        except asyncio.CancelledError:
            print(json.dumps({"cancelled": True, "state": controller.get_state()}))
            return
        raise AssertionError("interruption was not injected")


if __name__ == "__main__":
    asyncio.run(main())
