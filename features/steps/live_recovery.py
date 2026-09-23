import asyncio
import json
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from behave import then, when
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:19000"


async def god_call(tool, arguments=None):
    token = json.loads((ROOT / "secrets/http/mcp-tokens.json").read_text())["god"]
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}, timeout=120) as http:
        async with streamable_http_client(URL + "/mcp", http_client=http) as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=120)
            ) as client:
                await client.initialize()
                return await client.call_tool(tool, arguments or {})


def god(tool, arguments=None):
    return asyncio.run(god_call(tool, arguments))


def restart():
    result = subprocess.run(
        ["docker", "compose", "-f", "compose/compose.json", "restart", "management"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert result.returncode == 0, result.stderr
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(URL + "/healthz", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise AssertionError("management restart timeout")


@when("God applies a core-link fault and the management process is restarted")
def live_restart(c):
    initial = god("get_fault_state").structuredContent
    applied = god(
        "apply_fault", {"scenario_id": "core-link-failure", "idempotency_key": str(uuid4())}
    )
    assert not applied.isError, applied
    try:
        restart()
        c.restarted = god("get_fault_state").structuredContent
        c.blocked = god(
            "apply_fault", {"scenario_id": "customer-bgp-failure", "idempotency_key": str(uuid4())}
        )
    finally:
        c.reset = god("reset_lab", {"idempotency_key": str(uuid4())})
        assert not c.reset.isError, c.reset
    c.original_generation = initial["generation"]


@then("the new process reports unverified reconciliation and blocks another apply")
def restart_state(c):
    state = c.restarted["data"]
    assert state["state"] == "reconciliation_required" and state["verified"] is False, state
    assert (
        c.blocked.isError and c.blocked.structuredContent["error_code"] == "reconciliation_required"
    )


@then("a fresh God reset restores the live lab and advances generation once")
def restart_reset(c):
    assert c.reset.structuredContent["generation"] == c.original_generation + 1
    assert (
        c.reset.structuredContent["data"]["verified"]
        and c.reset.structuredContent["data"]["state"] == "baseline"
    )


@when(
    'an isolated controller process is interrupted by "{mode}" after a real "{scenario}" mutation'
)
def ambiguous(c, mode, scenario):
    assert mode in {"crash", "cancel"} and scenario in {
        "core-link-failure",
        "customer-bgp-failure",
        "data-path-degradation",
    }
    directory = "/tmp/recovery-" + str(uuid4())
    source = (ROOT / "tests/mcp_harness/recovery_process.py").read_text()

    def run(action):
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "minicore-management-1",
                "python",
                "-",
                action,
                directory,
                scenario,
            ],
            input=source,
            capture_output=True,
            text=True,
            timeout=100,
        )

    recovered = None
    try:
        interrupted = run(mode)
        assert interrupted.returncode == (77 if mode == "crash" else 0), interrupted.stderr
    finally:
        # Always exercise real reset even if interruption assertions fail.
        recovered = run("recover")
        if recovered.returncode != 0:
            # Host safety fallback uses only the fixed reset opcode, never arbitrary node shell.
            cleanup = (
                "import asyncio;from pathlib import Path;from minicore_mcp.model import Topology;from minicore_mcp.ssh_adapter import SSHAdapter;from minicore_mcp.fault_executor import FaultExecutor;t=Topology(Path('/app/inventory/topology.json'),Path('/runtime/observations.json'));e=FaultExecutor(t,SSHAdapter(t,Path('/run/ssh-client')),Path('/run/fault-client'));asyncio.run(e.mutate('"
                + scenario
                + "','reset'));assert asyncio.run(e.verify_baseline())"
            )
            safe = subprocess.run(
                ["docker", "exec", "minicore-management-1", "python", "-c", cleanup],
                capture_output=True,
                text=True,
                timeout=90,
            )
            assert safe.returncode == 0, safe.stderr
        # Synchronise the production generation after out-of-band acceptance work.
        result = god("reset_lab", {"idempotency_key": str(uuid4())})
        assert not result.isError, result
    assert recovered.returncode == 0, recovered.stderr
    c.recovery = json.loads(recovered.stdout)
    c.recovery.update(mode=mode, scenario=scenario)


@then("its new process loads reconciliation_required without verified success")
def ambiguous_state(c):
    assert (
        c.recovery["before"]["state"] == "reconciliation_required"
        and c.recovery["before"]["verified"] is False
    )


@then("explicit recovery restores actual peers and packets and records one new generation")
def ambiguous_reset(c):
    assert (
        c.recovery["after"]["state"] == "baseline"
        and c.recovery["after"]["verified"]
        and c.recovery["replay_equal"]
    )
    assert c.recovery["after"]["generation"] == c.recovery["before"]["generation"] + 1
    path = (
        ROOT
        / "reports"
        / ("recovery-" + c.recovery["mode"] + "-" + c.recovery["scenario"] + ".json")
    )
    path.write_text(json.dumps(c.recovery, indent=2) + "\n")
