import json
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx
from behave import given, then, when

ROOT = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:19000"


def request(c, action, body):
    response = httpx.post(
        URL + "/api/v1/faults/" + action, headers=c.target_headers, json=body, timeout=100
    )
    assert response.status_code == 200, response.text
    value = response.json()
    assert not value["error_code"], value
    return value


def restore(c):
    c.target_restore = request(c, "reset", {"idempotency_key": str(uuid4())})


@given("the local targeted host executor is enabled and baseline is verified")
def target_live_fixture(c):
    tokens = json.loads((ROOT / "secrets/http/mcp-tokens.json").read_text())
    c.target_headers = {
        "Authorization": "Bearer " + tokens["god"],
        "Origin": URL,
        "Content-Type": "application/json",
        "X-Minicore-Intent": "fault-control",
    }
    assert httpx.get(URL + "/api/v1/view", headers=c.target_headers).json()["fault_control"]
    restore(c)
    c.initial_generation = c.target_restore["data"]["generation"]

    def cleanup():
        # Preserve the scenario's explicit reset evidence for failure diagnosis.
        c.cleanup_restore = request(c, "reset", {"idempotency_key": str(uuid4())})

    c.add_cleanup(cleanup)


@when("God zaps node pe1 through the browser command endpoint")
def targeted_stop(c):
    c.target_applied = request(
        c,
        "apply",
        {"mode": "zap", "target_type": "node", "target_id": "pe1", "idempotency_key": str(uuid4())},
    )


@then("the pe1 container is stopped and Operator inspection cannot execute there")
def node_stopped(c):
    value = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.State.Running}}", "minicore-pe1-1"], text=True
    ).strip()
    assert value == "false"
    data = httpx.get(URL + "/api/v1/nodes/pe1/observations", timeout=30).json()["data"]
    assert data["interfaces"]["error_code"] and data["interfaces"]["data"] is None


@when("God zaps link p1-p2 through the browser command endpoint")
def targeted_link(c):
    c.target_applied = request(
        c,
        "apply",
        {
            "mode": "zap",
            "target_type": "link",
            "target_id": "p1-p2",
            "idempotency_key": str(uuid4()),
        },
    )


@then("both endpoint interfaces are down while both containers keep running")
def link_stopped(c):
    for node, interface in [("p1", "to-p2"), ("p2", "to-p1")]:
        data = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "exec",
                    f"minicore-{node}-1",
                    "ip",
                    "-j",
                    "link",
                    "show",
                    "dev",
                    interface,
                ],
                text=True,
            )
        )
        assert "UP" not in data[0]["flags"]
        assert (
            subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.Running}}", f"minicore-{node}-1"],
                text=True,
            ).strip()
            == "true"
        )


@when("God rolls dice on ce1 and retries the same browser request")
def targeted_roll(c):
    body = {
        "mode": "dice",
        "target_type": "node",
        "target_id": "ce1",
        "idempotency_key": str(uuid4()),
    }
    c.target_applied = request(c, "apply", body)
    c.target_replayed = request(c, "apply", body)


@then("the same selected corruption is verified once and the request cannot be rerolled")
def roll_verified(c):
    assert (
        c.target_replayed == c.target_applied
        and c.target_applied["data"]["scenario_id"].startswith("corrupt-")
        and c.target_applied["data"]["verified"]
    )


@then("explicit God restore starts the container and verifies all peers and packets")
def target_restore_verified(c):
    restore(c)
    assert (
        c.target_restore["data"]["verified"]
        and c.target_restore["data"]["state"] == "baseline"
        and c.target_restore["data"]["generation"] == c.initial_generation + 1
    )


def host_request(scenario, action):
    script = (
        "import asyncio,json;from pathlib import Path;from minicore_mcp.host_faults import HostAdapter;print(json.dumps(asyncio.run(HostAdapter(Path('/run/host-control/fault.sock')).mutate('"
        + scenario
        + "','"
        + action
        + "'))))"
    )
    result = subprocess.run(
        ["docker", "exec", "minicore-management-1", "python", "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@when('the fixed host catalogue applies "{scenario}" and records actual node evidence')
def measure_corruption(c, scenario):
    assert scenario in {
        "corrupt-delay-link-host1-ce1",
        "corrupt-loss-link-host1-ce1",
        "corrupt-route-node-ce1",
    }
    try:
        applied = host_request(scenario, "apply")
        assert applied["ok"], applied
        if "route" in scenario:
            routes = json.loads(
                subprocess.check_output(
                    [
                        "docker",
                        "exec",
                        "minicore-ce1-1",
                        "ip",
                        "-j",
                        "route",
                        "show",
                        "exact",
                        "10.200.9.0/29",
                    ],
                    text=True,
                )
            )
            assert any(
                r.get("type") == "blackhole"
                and r.get("metric") == 1
                and str(r.get("protocol")) == "198"
                for r in routes
            ), routes
            ping = subprocess.run(
                ["docker", "exec", "minicore-host1-1", "ping", "-c", "3", "-W", "1", "10.200.9.2"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert ping.returncode != 0, ping.stdout
            c.corruption_measured = {"scenario": scenario, "traffic_blocked": True}
        else:
            qdisc = json.loads(
                subprocess.check_output(
                    [
                        "docker",
                        "exec",
                        "minicore-ce1-1",
                        "tc",
                        "-j",
                        "qdisc",
                        "show",
                        "dev",
                        "to-host1",
                    ],
                    text=True,
                )
            )
            effect = next(q for q in qdisc if q.get("handle") == "1234:")
            assert effect["kind"] == "netem"
            if "delay" in scenario:
                assert effect["options"]["delay"]["delay"] == 0.1, effect
            else:
                assert abs(effect["options"]["loss-random"]["loss"] - 0.25) < 0.0001, effect
            c.corruption_measured = {"scenario": scenario, "qdisc": effect}
    finally:
        recovered = host_request(scenario, "reset")
        assert recovered["ok"], recovered
        restore(c)


@then("the selected corruption has its measured effect and explicit recovery removes it")
def measured_recovered(c):
    assert c.corruption_measured and c.target_restore["data"]["verified"]
    path = ROOT / "reports" / ("measured-" + c.corruption_measured["scenario"] + ".json")
    path.write_text(json.dumps(c.corruption_measured, indent=2) + "\n")


@when("God stops host1 and the host executor restarts")
def restart_owned_endpoint(c):
    c.target_applied = request(
        c,
        "apply",
        {
            "mode": "zap",
            "target_type": "node",
            "target_id": "host1",
            "idempotency_key": str(uuid4()),
        },
    )
    assert (
        subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.Running}}", "minicore-host1-1"], text=True
        ).strip()
        == "false"
    )
    result = subprocess.run(
        ["sh", "scripts/host-fault-service.sh", "restart"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    import time

    time.sleep(1)


@then("the stopped endpoint remains owned and God restore brings back endpoint traffic")
def restarted_owned(c):
    journal = json.loads((ROOT / "runtime/host-fault-journal/state.json").read_text())
    assert journal["scenario"] == "zap-node-host1"
    restore(c)
    assert c.target_restore["data"]["verified"]
    assert (
        subprocess.run(
            ["docker", "exec", "minicore-host1-1", "ping", "-c", "2", "-W", "1", "10.200.9.2"],
            capture_output=True,
            timeout=8,
        ).returncode
        == 0
    )
