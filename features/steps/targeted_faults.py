import asyncio
import json

from behave import given, then, when


@given("a targeted controller with a recording host executor")
def targeted(c):
    from minicore_mcp.faults import FaultController

    assert hasattr(c.server, "targeted_fault"), "targeted God fault contract is unavailable"
    from minicore_mcp import host_faults

    c.host_module = host_faults

    class Executor:
        def __init__(self):
            self.calls = []

        async def verify_baseline(self):
            return True

        async def mutate(self, scenario, action):
            self.calls.append((scenario, action))
            return {"ok": True, "verified": True}

    c.host_executor = Executor()
    c.server.controller = FaultController(
        c.topology,
        c.host_executor,
        c.root / "targeted",
        catalogue=host_faults.catalogue(c.topology.inventory),
    )
    c.server.browser_origin = "http://127.0.0.1:19000"


def invoke(c, target_type, target_id, mode, key="target-key-001"):
    return asyncio.run(
        c.server.targeted_fault(
            {
                "target_type": target_type,
                "target_id": target_id,
                "mode": mode,
                "idempotency_key": key,
            },
            "god",
        )
    )


@when("God requests a zap of node pe1")
def zap_node(c):
    c.target_result = invoke(c, "node", "pe1", "zap")


@then("the fixed host request stops only the inventoried pe1 service")
def stop_node(c):
    scenario = c.host_executor.calls[0][0]
    commands = c.host_module.commands(c.topology.inventory, scenario, "apply")
    assert commands == [["docker", "stop", "--time", "2", "minicore-pe1-1"]], commands
    assert c.target_result["data"]["target_id"] == "pe1"


@then("reset restarts it and verifies baseline before advancing generation")
def reset_node(c):
    result = asyncio.run(c.server.controller.reset("target-reset-001", "god"))
    assert result["data"]["state"] == "baseline" and result["data"]["generation"] == 2
    scenario = c.host_executor.calls[0][0]
    assert c.host_module.commands(c.topology.inventory, scenario, "reset") == [
        ["docker", "start", "minicore-pe1-1"]
    ]


@when("God requests a zap of link p1-p2")
def zap_link(c):
    c.target_result = invoke(c, "link", "p1-p2", "zap")


@then("both link endpoints are disabled and no container stop is compiled")
def down_link(c):
    commands = c.host_module.commands(c.topology.inventory, c.host_executor.calls[0][0], "apply")
    assert len(commands) == 2 and all(
        cmd[:2] == ["docker", "exec"] and cmd[-1] == "down" for cmd in commands
    ), commands
    assert {cmd[2] for cmd in commands} == {"minicore-p1-1", "minicore-p2-1"}


@when("God rolls corruption on node ce1 and repeats the request key")
def dice_retry(c):
    c.first_target = invoke(c, "node", "ce1", "dice")
    c.second_target = invoke(c, "node", "ce1", "dice")


@then("one bounded corruption is executed and both responses name the same chosen fault")
def one_roll(c):
    assert len(c.host_executor.calls) == 1 and c.first_target == c.second_target
    assert c.first_target["data"]["scenario_id"].startswith("corrupt-")


@when('"{role}" submits a browser fault with "{condition}"')
def browser_denial(c, role, condition):
    headers = {
        "authorization": "Bearer " + role[0] * 40,
        "origin": "http://127.0.0.1:19000",
        "content-type": "application/json",
        "x-minicore-intent": "fault-control",
    }
    body = {
        "mode": "zap",
        "target_type": "node",
        "target_id": "p1",
        "idempotency_key": "browser-key-001",
    }
    if condition == "missing origin":
        headers.pop("origin")
    if condition == "foreign origin":
        headers["origin"] = "https://evil.example"
    if condition == "missing intent":
        headers.pop("x-minicore-intent")
    if condition == "unknown target":
        body["target_id"] = "management"
    if condition == "arbitrary argument":
        body["command"] = "rm -rf /"
    c.browser_result = asyncio.run(
        c.server.handle_http_request_async(
            method="POST",
            path="/api/v1/faults/apply",
            headers=headers,
            body=json.dumps(body).encode(),
            peer="127.0.0.1",
        )
    )


@then("no host mutation executes and the browser request is rejected")
def rejected(c):
    assert c.browser_result.status in {400, 403} and not c.host_executor.calls


@when("God submits a valid browser fault and resets with a new key")
def browser_apply_reset(c):
    browser_denial(c, "god", "valid")
    c.browser_apply = c.browser_result
    c.browser_result = asyncio.run(
        c.server.handle_http_request_async(
            method="POST",
            path="/api/v1/faults/reset",
            headers={
                "authorization": "Bearer " + "g" * 40,
                "origin": "http://127.0.0.1:19000",
                "content-type": "application/json",
                "x-minicore-intent": "fault-control",
            },
            body=b'{"idempotency_key":"browser-reset-001"}',
            peer="127.0.0.1",
        )
    )


@then("both actions use the same audited controller and restore baseline")
def browser_ok(c):
    assert c.browser_apply.status == 200 and c.browser_result.status == 200
    assert len(c.host_executor.calls) == 2 and c.server.controller.get_state()["generation"] == 2


@when("the host receives unknown targets arbitrary commands or extra request fields")
def host_invalid(c):
    assert hasattr(c.host_module, "decode"), "host request validation is unavailable"
    c.host_denials = []
    for value in [
        {"scenario": "zap-node-management", "action": "apply"},
        {"scenario": "zap-node-p1", "action": "exec"},
        {"scenario": "zap-node-p1", "action": "apply", "command": "id"},
    ]:
        try:
            c.host_module.decode(json.dumps(value).encode(), c.topology.inventory)
        except ValueError:
            c.host_denials.append(True)
        else:
            c.host_denials.append(False)


@then("all host requests are denied before Docker execution")
def host_denied(c):
    assert c.host_denials == [True, True, True]


@then("published controller state excludes the durable intent map")
def intents_private(c):
    assert "target_intents" not in c.server.controller.get_state()
