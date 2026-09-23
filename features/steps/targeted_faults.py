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


def host_fixture(c):
    import importlib.util
    from pathlib import Path

    module_spec = importlib.util.spec_from_file_location(
        "test_host_controller",
        Path(__file__).resolve().parents[2] / "scripts/host-fault-controller.py",
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    module.JOURNAL = c.root / "host-journal.json"
    return module


@when("the host receives reset with no owned fault journal")
def no_owned_reset(c):
    from unittest.mock import AsyncMock, patch

    module = host_fixture(c)
    with patch.object(module, "run", new_callable=AsyncMock) as run:
        c.host_result = asyncio.run(module.execute({"scenario": "zap-node-p1", "action": "reset"}))
        c.host_executions = run.call_count


@then("it returns unchanged success without executing Docker")
def no_unowned_change(c):
    assert c.host_result["ok"] and c.host_executions == 0


@when("a data interface already has an unowned netem rule")
def foreign_netem(c):
    from unittest.mock import AsyncMock, patch

    module = c.host_test = host_fixture(c)
    run = AsyncMock(
        return_value=(
            0,
            b'[{"kind":"netem","handle":"4321:","root":true,"options":{"delay":100000}}]',
            b"",
        )
    )
    with patch.object(module, "run", run):
        try:
            c.foreign_result = asyncio.run(
                module.execute({"scenario": "corrupt-delay-link-p1-p2", "action": "apply"})
            )
        except ValueError as exc:
            c.foreign_result = {"error_code": str(exc)}
    c.host_argv = [call.args[0] for call in run.call_args_list]


@then("targeted corruption is denied and no ownership is recorded")
def foreign_denied(c):
    assert c.foreign_result["error_code"] == "foreign_qdisc", c.foreign_result
    assert not c.host_test.JOURNAL.exists()
    assert all("add" not in args and "del" not in args for args in c.host_argv)


@when("the host applies and resets a selected node with a simulated Docker executor")
def journal_sequence(c):
    from unittest.mock import patch

    module = c.host_test = host_fixture(c)
    running = True
    c.host_recorded = []

    async def run(argv):
        nonlocal running
        if argv[1] == "inspect":
            return (0, b"true" if running else b"false", b"")
        assert module.JOURNAL.exists(), "host ownership missing before mutation"
        journal = json.loads(module.JOURNAL.read_text())
        assert journal["scenario"] == "zap-node-p1"
        c.host_recorded.append(argv[1])
        running = argv[1] == "start"
        return (0, b"", b"")

    with patch.object(module, "run", run):
        c.host_apply = asyncio.run(module.execute({"scenario": "zap-node-p1", "action": "apply"}))
        assert module.JOURNAL.exists()
        c.host_reset = asyncio.run(module.execute({"scenario": "zap-node-p1", "action": "reset"}))


@then("ownership is durable before stop and removed only after verified start")
def journal_verified(c):
    assert c.host_apply["ok"] and c.host_reset["ok"] and c.host_recorded == ["stop", "start"]
    assert not c.host_test.JOURNAL.exists()


@when("a host command emits its JSON in separated pipe writes")
def host_chunked(c):
    import sys

    module = host_fixture(c)
    c.chunks = asyncio.run(
        module.run(
            [
                sys.executable,
                "-c",
                'import sys,time;sys.stdout.write("{\\"running\\":");sys.stdout.flush();time.sleep(.1);sys.stdout.write("true}");sys.stdout.flush()',
            ]
        )
    )


@then("the host receives the complete JSON before verifying a mutation")
def host_complete(c):
    assert c.chunks[0] == 0 and json.loads(c.chunks[1]) == {"running": True}


@when("the host compiles a customer-prefix blackhole")
def compile_blackhole(c):
    c.route_argv = c.host_module.commands(c.topology.inventory, "corrupt-route-node-ce1", "apply")[
        0
    ]


@then("its fixed metric wins over BGP and it is not labelled as a BGP-owned route")
def blackhole_priority(c):
    assert c.route_argv[c.route_argv.index("metric") + 1] == "1"
    assert c.route_argv[c.route_argv.index("proto") + 1] == "198"


@when("tc reports a nested 0.1 second delay for an owned queue")
def nested_delay(c):
    module = host_fixture(c)
    assert hasattr(module, "netem_matches"), "netem parameter parser unavailable"
    c.delay_matches = module.netem_matches(
        {"delay": {"delay": 0.1, "jitter": 0, "correlation": 0}}, "delay"
    )


@then("the host recognises the configured 100 millisecond delay")
def nested_matches(c):
    assert c.delay_matches


@when("God rolls corruption then its result expires after recovery")
def evicted_roll(c):
    invoke(c, "node", "ce1", "dice")
    asyncio.run(c.server.controller.reset("evict-reset-key", "god"))
    c.server.controller.state["results"].pop("target-key-001")
    c.calls_before = len(c.host_executor.calls)


@then("retrying the retained intent returns idempotency_expired without a new mutation")
def expired_retry(c):
    result = invoke(c, "node", "ce1", "dice")
    assert (
        result["error_code"] == "idempotency_expired"
        and len(c.host_executor.calls) == c.calls_before
    ), result


@when("the targeted intent journal is corrupted and the controller restarts")
def corrupted_intents(c):
    from minicore_mcp.faults import FaultController

    c.server.controller.state["target_intents"] = {
        "bad-key-001": {"request": [], "scenario": "zap-node-management"}
    }
    c.server.controller.save()
    c.server.controller = FaultController(
        c.topology,
        c.host_executor,
        c.root / "targeted",
        catalogue=c.host_module.catalogue(c.topology.inventory),
    )


@then("targeted apply requires reconciliation and publishes no corrupt private intent")
def corrupt_closed(c):
    result = invoke(c, "node", "p1", "zap")
    assert result["error_code"] == "reconciliation_required" and not c.host_executor.calls, result
    assert "target_intents" not in c.server.controller.get_state()


@when("God submits invalid UTF-8 to the browser fault endpoint")
def bad_encoding(c):
    c.browser_result = asyncio.run(
        c.server.handle_http_request_async(
            method="POST",
            path="/api/v1/faults/apply",
            headers={
                "authorization": "Bearer " + "g" * 40,
                "origin": "http://127.0.0.1:19000",
                "content-type": "application/json",
                "x-minicore-intent": "fault-control",
            },
            body=b"\xff\xff",
            peer="127.0.0.1",
        )
    )
