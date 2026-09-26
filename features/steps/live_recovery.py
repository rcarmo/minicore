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
    if tool == "reset_lab":
        # Preserve only the bounded public controller projection before cleanup.
        # Never collect credentials or the private journal into test artifacts.
        try:
            before = asyncio.run(god_call("get_fault_state"))
            path = ROOT / "reports/recovery-pre-reset.json"
            records = json.loads(path.read_text()) if path.exists() else []
            records.append(
                {
                    "reset_key": (arguments or {}).get("idempotency_key"),
                    "controller": before.structuredContent,
                }
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(records[-32:], indent=2) + "\n")
        except Exception:
            pass  # Never prevent the safety reset because evidence capture failed.
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


def wire_session():
    token = json.loads((ROOT / "secrets/http/mcp-tokens.json").read_text())["god"]
    headers = {
        "Authorization": "Bearer " + token,
        "MCP-Protocol-Version": "2025-03-26",
        "Accept": "application/json, text/event-stream",
    }
    response = httpx.post(
        URL + "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "wire-loss-test", "version": "1"},
            },
        },
    )
    assert response.status_code == 200, response.text
    headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
    return headers


def raw_mutation(headers, tool, key, request_id, scenario=None):
    import socket

    args = {"idempotency_key": key}
    if scenario:
        args["scenario_id"] = scenario
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
    ).encode()
    lines = [
        "POST /mcp HTTP/1.1",
        "Host: 127.0.0.1:19000",
        "Content-Type: application/json",
        f"Content-Length: {len(payload)}",
        *[f"{k}: {v}" for k, v in headers.items()],
    ]
    sock = socket.create_connection(("127.0.0.1", 19000), timeout=10)
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode() + payload)
    return sock


@when("a God TCP caller disconnects immediately after sending a fixed apply")
def lost_god_response(c):
    headers = wire_session()
    key = str(uuid4())
    before = god("get_fault_state").structuredContent["generation"]
    try:
        sock = raw_mutation(headers, "apply_fault", key, "lost-apply-001", "core-link-failure")
        sock.close()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = god("get_fault_state").structuredContent["data"]
            if state["state"] == "active":
                break
            time.sleep(0.1)
        assert state["state"] == "active", state
        c.replayed_apply = god(
            "apply_fault", {"scenario_id": "core-link-failure", "idempotency_key": key}
        )
        c.lost_generation = before
    finally:
        c.lost_reset = god("reset_lab", {"idempotency_key": str(uuid4())})
        assert not c.lost_reset.isError, c.lost_reset
        httpx.delete(URL + "/mcp", headers=headers)


@then(
    "a retry with that key returns the single recorded outcome and explicit reset restores baseline"
)
def loss_reconciled(c):
    assert (
        not c.replayed_apply.isError
        and c.replayed_apply.structuredContent["generation"] == c.lost_generation
    )
    assert (
        c.lost_reset.structuredContent["generation"] == c.lost_generation + 1
        and c.lost_reset.structuredContent["data"]["verified"]
    )


@when("God cancels its reset request while baseline verification is in progress")
def wire_cancel_reset(c):
    headers = wire_session()
    sock = None
    before = god("get_fault_state").structuredContent["generation"]
    try:
        applied = god(
            "apply_fault", {"scenario_id": "core-link-failure", "idempotency_key": str(uuid4())}
        )
        assert not applied.isError
        sock = raw_mutation(headers, "reset_lab", str(uuid4()), "cancel-reset-001")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = god("get_fault_state").structuredContent
            if state["data"]["state"] == "resetting":
                break
            time.sleep(0.03)
        assert state["data"]["state"] == "resetting", state
        cancel = httpx.post(
            URL + "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": "cancel-reset-001"},
            },
        )
        assert cancel.status_code == 202, cancel.text
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = god("get_fault_state").structuredContent
            if state["data"]["state"] == "reconciliation_required":
                break
            time.sleep(0.05)
        c.cancel_state = state
        c.cancel_before = before
    finally:
        if sock:
            sock.close()
        c.cancel_recovered = god("reset_lab", {"idempotency_key": str(uuid4())})
        assert not c.cancel_recovered.isError, c.cancel_recovered
        httpx.delete(URL + "/mcp", headers=headers)


@then(
    "the reset reports uncertainty and a new reset recovers without premature generation advancement"
)
def wire_cancel_safe(c):
    assert (
        c.cancel_state["data"]["state"] == "reconciliation_required"
        and c.cancel_state["generation"] == c.cancel_before
    ), c.cancel_state
    assert (
        c.cancel_recovered.structuredContent["generation"] == c.cancel_before + 1
        and c.cancel_recovered.structuredContent["data"]["verified"]
    )


@when(
    "the real fault key attempts shell configuration wrong-node unknown-scenario PTY and forwarding requests"
)
def fault_escapes(c):
    prefix = [
        "docker",
        "exec",
        "-i",
        "minicore-management-1",
        "ssh",
        "-i",
        "/run/fault-client/fault",
        "-o",
        "UserKnownHostsFile=/run/fault-client/known_hosts",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "BatchMode=yes",
    ]
    c.escape_results = []
    for command, payload in [
        ("id", "{}"),
        ("minicore-fault", '{"operation":"configure","command":"shutdown"}'),
        (
            "minicore-fault",
            '{"operation":"fault","scenario":"customer-bgp-failure","action":"apply"}',
        ),
        ("minicore-fault", '{"operation":"fault","scenario":"unknown","action":"apply"}'),
    ]:
        result = subprocess.run(
            prefix + ["root@172.30.250.11", command],
            input=payload,
            capture_output=True,
            text=True,
            timeout=15,
        )
        c.escape_results.append(result)
    c.pty = subprocess.run(
        prefix + ["-tt", "root@172.30.250.11", "id"], capture_output=True, text=True, timeout=15
    )
    c.forward = subprocess.run(
        prefix
        + ["-o", "ExitOnForwardFailure=yes", "-R", "0:127.0.0.1:22", "-N", "root@172.30.250.11"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    c.escape_baseline = god("get_fault_state").structuredContent["data"]


@then("every escape is rejected without a mutation or configuration write")
def fault_escape_denied(c):
    for result in c.escape_results:
        value = json.loads(result.stdout)
        assert value["status"] == "error" and "uid=" not in result.stdout, value
    assert "PTY allocation request failed" in c.pty.stderr
    assert c.forward.returncode != 0 and "forwarding failed" in c.forward.stderr
    assert c.escape_baseline["state"] == "baseline"
    result = subprocess.run(
        ["docker", "exec", "minicore-p1-1", "ip", "-j", "link", "show", "to-p2"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "UP" in json.loads(result.stdout)[0]["flags"]


@then("Operator evidence cannot disclose HTTP tokens or SSH private keys")
def secret_boundary(c):
    tokens = json.loads((ROOT / "secrets/http/mcp-tokens.json").read_text())
    header = {"Authorization": "Bearer " + tokens["operator"]}
    bodies = []
    for path in [
        "/api/v1/topology",
        "/api/v1/nodes/p1/config/frr.conf",
        "/api/v1/nodes/p1/logs",
        "/api/v1/routing?prefix=10.200.8.0/29",
        "/run/fault-client/fault",
        "/secrets/http/mcp-tokens.json",
        "/api/v1/topology?view=god",
    ]:
        response = httpx.get(URL + path, headers=header, timeout=30)
        bodies.append(response.text)
        if path.startswith("/run/") or path.startswith("/secrets/"):
            assert response.status_code == 404
        if path.endswith("view=god"):
            assert response.status_code == 403
    value = "\n".join(bodies)
    assert all(token not in value for token in tokens.values())
    assert "PRIVATE KEY" not in value


@when("a customer fault removes CE1 reachability and Operator probes the far endpoint")
def live_no_route(c):
    try:
        applied = god(
            "apply_fault", {"scenario_id": "customer-bgp-failure", "idempotency_key": str(uuid4())}
        )
        assert not applied.isError, applied
        result = subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                str(ROOT / "tests/mcp_harness/tool_cli.py"),
                "operator",
                "ping",
                json.dumps({"node_id": "ce1", "destination": "10.200.9.2", "count": 2}),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        c.no_route_result = json.loads(result.stdout)
    finally:
        reset = god("reset_lab", {"idempotency_key": str(uuid4())})
        assert not reset.isError, reset


@then("the probe reports network_unreachable without fabricated packet counts and reset recovers")
def live_no_route_assert(c):
    result = c.no_route_result
    assert (
        result["isError"]
        and result["evidence"]["error_code"] == "network_unreachable"
        and result["evidence"]["data"] is None
    ), result
