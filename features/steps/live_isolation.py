"""Host-owned destructive isolation acceptance; fixed lab targets, always restore."""

import json
import subprocess
import time
from pathlib import Path

import httpx
from behave import given, then, when

ROOT = Path(__file__).resolve().parents[2]


def docker(node, *args):
    return subprocess.run(
        ["docker", "exec", f"minicore-{node}-1", *args], capture_output=True, text=True, timeout=25
    )


def ping(node, target):
    return docker(node, "ping", "-n", "-c", "2", "-W", "1", target).returncode == 0


def diagnostic(node):
    r = httpx.get(
        f"http://127.0.0.1:19000/api/v1/nodes/{node}/routes?prefix=10.200.8.0/29", timeout=20
    )
    assert r.status_code == 200, r.text


def baseline():
    result = subprocess.run(
        [
            "docker",
            "exec",
            "minicore-management-1",
            "python",
            "-c",
            "import asyncio;from pathlib import Path;from minicore_mcp.model import Topology;from minicore_mcp.fault_executor import FaultExecutor;from minicore_mcp.ssh_adapter import SSHAdapter;t=Topology(Path('/app/inventory/topology.json'),Path('/runtime/observations.json'));assert asyncio.run(FaultExecutor(t,SSHAdapter(t,Path('/run/ssh-client')),Path('/run/fault-client')).verify_baseline())",
        ],
        capture_output=True,
        text=True,
        timeout=80,
    )
    assert result.returncode == 0, result.stderr


@given("the complete local lab is healthy and the fault controller is at baseline")
def isolated_lab(c):
    # State is read inside management; no private journal/keys are emitted.
    result = subprocess.run(
        [
            "docker",
            "exec",
            "minicore-management-1",
            "python",
            "-c",
            "import json;assert json.load(open('/control/state.json'))['state']=='baseline'",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    c.isolation = {}


@when("each endpoint probes its local management address and Docker bridge gateway")
def probe_boundaries(c):
    c.boundary_probes = {}
    for node, targets in [
        ("host1", ["172.30.250.15", "172.30.250.2", "10.200.8.1"]),
        ("host2", ["172.30.250.16", "172.30.250.2", "10.200.9.1"]),
    ]:
        for target in targets:
            c.boundary_probes[node + ":" + target] = ping(node, target)


@then("all management and host gateway probes fail")
def boundary_denied(c):
    assert not any(c.boundary_probes.values()), c.boundary_probes


@then("restricted management diagnostics still succeed for every router")
def management_ok(c):
    for node in ["p1", "p2", "pe1", "pe2", "ce1", "ce2"]:
        diagnostic(node)


@when("packet capture observes bidirectional endpoint traffic across the provider")
def capture_path(c):
    captures = {}
    children = []
    try:
        for node in ["p1", "p2", "pe1", "pe2", "ce1", "ce2"]:
            pid = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.Pid}}", f"minicore-{node}-1"], text=True
            ).strip()
            child = subprocess.Popen(
                [
                    "sudo",
                    "timeout",
                    "8",
                    "nsenter",
                    "-t",
                    pid,
                    "-n",
                    "tcpdump",
                    "-l",
                    "-nn",
                    "-i",
                    "any",
                    "icmp and src host 10.200.8.2 and dst host 10.200.9.2",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            children.append((node, child))
        time.sleep(1)
        assert ping("host1", "10.200.9.2") and ping("host2", "10.200.8.2")
        for node, child in children:
            out, err = child.communicate(timeout=12)
            assert child.returncode in {0, 124}, err
            captures[node] = out
    finally:
        for _, child in children:
            if child.poll() is None:
                child.kill()
                child.wait()
    c.captures = captures


@then("request packets traverse CE1, PE1, a core router, PE2 and CE2 without a management hop")
def traced(c):
    for node in ["pe1", "pe2", "ce1", "ce2"]:
        assert "ICMP echo request" in c.captures[node], c.captures
    assert any("ICMP echo request" in c.captures[n] for n in ["p1", "p2"]), c.captures
    assert all("mgmt0" not in out for out in c.captures.values()), c.captures


@when("both PE1 provider interfaces are disabled temporarily")
def cut_paths(c):
    c.cut_results = {}
    try:
        for interface in ["to-p1", "to-p2"]:
            assert docker("pe1", "ip", "link", "set", "dev", interface, "down").returncode == 0
        c.cut_results["forward"] = ping("host1", "10.200.9.2")
        c.cut_results["reverse"] = ping("host2", "10.200.8.2")
        for node in ["p1", "p2", "pe1", "pe2", "ce1", "ce2"]:
            diagnostic(node)
        c.cut_results["management"] = True
        # Try both host bridge gateway and peer CE management interface as shortcuts.
        shortcuts = []
        try:
            docker("host1", "ip", "route", "replace", "10.200.9.0/29", "via", "10.200.8.1")
            shortcuts.append(ping("host1", "10.200.9.2"))
        finally:
            docker("host1", "ip", "route", "del", "10.200.9.0/29")
        try:
            assert (
                docker(
                    "ce1",
                    "ip",
                    "route",
                    "replace",
                    "10.200.9.0/29",
                    "via",
                    "172.30.250.16",
                    "dev",
                    "mgmt0",
                ).returncode
                == 0
            )
            shortcuts.append(ping("host1", "10.200.9.2"))
        finally:
            docker(
                "ce1", "ip", "route", "del", "10.200.9.0/29", "via", "172.30.250.16", "dev", "mgmt0"
            )
        c.cut_results["shortcuts"] = shortcuts
    finally:
        for interface in ["to-p1", "to-p2"]:
            assert docker("pe1", "ip", "link", "set", "dev", interface, "up").returncode == 0
        baseline()
        c.cut_results["recovered"] = ping("host1", "10.200.9.2") and ping("host2", "10.200.8.2")


@then("endpoint traffic fails in both directions while management diagnostics succeed")
def cut_denied(c):
    assert (
        c.cut_results["management"]
        and not c.cut_results["forward"]
        and not c.cut_results["reverse"]
    ), c.cut_results


@then("host-gateway and management-next-hop shortcut attempts fail")
def shortcuts_denied(c):
    assert c.cut_results["shortcuts"] == [False, False], c.cut_results


@then("restoring both links recovers peerings and bidirectional endpoint traffic")
def recovered(c):
    assert c.cut_results["recovered"]
    report = ROOT / "reports/isolation.json"
    report.write_text(json.dumps({"captures": c.captures, "cut": c.cut_results}, indent=2) + "\n")


@then("only management loopback port 19000 is published and routers have no default route")
def ingress(c):
    for node in ["p1", "p2", "pe1", "pe2", "ce1", "ce2", "host1", "host2"]:
        value = json.loads(
            subprocess.check_output(["docker", "inspect", f"minicore-{node}-1"], text=True)
        )[0]
        assert not value["HostConfig"]["PortBindings"]
        if node not in {"host1", "host2"}:
            assert "default" not in docker(node, "ip", "route").stdout
    value = json.loads(
        subprocess.check_output(["docker", "inspect", "minicore-management-1"], text=True)
    )[0]
    assert value["HostConfig"]["PortBindings"] == {
        "9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "19000"}]
    }


@then("all data bridges are internal without host gateway access or masquerading")
def bridges(c):
    inventory = json.loads((ROOT / "inventory/topology.json").read_text())
    for link in inventory["links"]:
        value = json.loads(
            subprocess.check_output(
                ["docker", "network", "inspect", "minicore_" + link["network"]], text=True
            )
        )[0]
        assert value["Internal"]
        assert value["Options"].get("com.docker.network.bridge.gateway_mode_ipv4") == "isolated"
        assert value["Options"].get("com.docker.network.bridge.enable_ip_masquerade") == "false"


@then("external diagnostic targets are denied before node execution")
def external_denied(c):
    token = json.loads((ROOT / "secrets/http/mcp-tokens.json").read_text())["operator"]
    response = httpx.post(
        "http://127.0.0.1:19000/mcp",
        headers={"Authorization": "Bearer " + token, "MCP-Protocol-Version": "2025-03-26"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": {"node_id": "ce1", "destination": "1.1.1.1"}},
        },
    )
    assert response.json()["error"]["message"] == "denied_destination", response.text
