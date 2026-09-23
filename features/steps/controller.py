import asyncio
import json
from unittest.mock import patch

from behave import given, then, when
from minicore_mcp.faults import FaultController


class RecordingExecutor:
    def __init__(self):
        self.calls = []
        self.verify_fault = True
        self.baseline = True

    async def mutate(self, scenario, action):
        self.calls.append((scenario, action))
        await asyncio.sleep(0.02)
        return {"ok": True, "verified": self.verify_fault if action == "apply" else True}

    async def verify_baseline(self):
        return self.baseline


@given("a controller with a recording constrained node executor")
def controller(c):
    c.executor = RecordingExecutor()
    c.control_dir = c.root / "control"
    c.controller = FaultController(c.topology, c.executor, c.control_dir)


@when("God applies the core-link scenario with a fresh request key")
def apply(c):
    c.control_result = asyncio.run(c.controller.apply("core-link-failure", "apply-key-001", "god"))


@then("the controller verifies the fault and records active state")
def applied(c):
    assert c.control_result["error_code"] is None and c.controller.get_state()["state"] == "active"


@then("replaying the same key returns the original outcome without another mutation")
def replay(c):
    before = list(c.executor.calls)
    r = asyncio.run(c.controller.apply("core-link-failure", "apply-key-001", "god"))
    assert r == c.control_result and c.executor.calls == before


@then("another scenario or changed key payload is rejected while active")
def conflicts(c):
    assert (
        asyncio.run(c.controller.apply("customer-bgp-failure", "other-key-001", "god"))[
            "error_code"
        ]
        == "fault_conflict"
    )
    assert (
        asyncio.run(c.controller.apply("customer-bgp-failure", "apply-key-001", "god"))[
            "error_code"
        ]
        == "idempotency_conflict"
    )


@when("God resets with a different request key")
def reset(c):
    c.reset_result = asyncio.run(c.controller.reset("reset-key-001", "god"))


@then("the fixed fault is removed and the routing baseline is verified")
def reset_verified(c):
    assert (
        c.reset_result["error_code"] is None
        and c.controller.get_state()["state"] == "baseline"
        and ("core-link-failure", "reset") in c.executor.calls
    )


@then("generation advances once and repeated reset is idempotent")
def reset_idempotent(c):
    assert c.topology.inventory["generation"] == 2
    before = list(c.executor.calls)
    assert asyncio.run(c.controller.reset("reset-key-001", "god")) == c.reset_result
    assert c.executor.calls == before


@given("the constrained executor will fail fault verification")
def failure(c):
    c.executor.verify_fault = False


@then("it attempts fixed reset and records verified baseline or reconciliation_required")
def rollback(c):
    assert ("core-link-failure", "reset") in c.executor.calls and c.controller.get_state()[
        "state"
    ] in {"baseline", "reconciliation_required"}


@then("it returns an error rather than active success")
def failed(c):
    assert c.control_result["error_code"] and c.controller.get_state()["state"] != "active"


@when("reset cannot verify healthy routing")
def failed_reset(c):
    c.executor.baseline = False
    reset(c)


@then("reset_failed is visible and another apply is rejected")
def failed_reset_result(c):
    assert c.reset_result["error_code"] == "reset_failed"
    assert (
        asyncio.run(c.controller.apply("core-link-failure", "another-key", "god"))["error_code"]
        == "reconciliation_required"
    )


@then("generation has not advanced")
def no_gen(c):
    assert c.topology.inventory["generation"] == 1


@when("the controller process restarts")
def restart(c):
    c.controller = FaultController(c.topology, c.executor, c.control_dir)


@then("it loads persisted active state and requires reconciliation before a new mutation")
def persisted(c):
    assert (
        c.controller.get_state()["state"] == "reconciliation_required"
        and c.controller.get_state()["scenario_id"] == "core-link-failure"
    )


@then("fixed reset can restore a verified baseline")
def reconcile(c):
    assert asyncio.run(c.controller.reset("recover-key", "god"))["error_code"] is None


@when("two God mutation requests overlap")
def concurrent(c):
    async def run():
        return await asyncio.gather(
            c.controller.apply("core-link-failure", "one-key-001", "god"),
            c.controller.apply("customer-bgp-failure", "two-key-001", "god"),
        )

    c.parallel = asyncio.run(run())


@then("only one executes and the other returns mutation_in_progress")
def serialized(c):
    assert len(c.executor.calls) == 1 and any(
        r["error_code"] == "mutation_in_progress" for r in c.parallel
    )


@given("the controller state directory is not writable")
def persistence_failure(c):
    # Patch only the atomic persistence seam; no chmod/root assumptions in this fixture.
    c.save_patch = patch.object(c.controller, "save", side_effect=OSError("read-only"))
    c.save_patch.start()
    c.add_cleanup(c.save_patch.stop)


@then("the executor is not called and the controller reports persistence_failed")
def fail_closed(c):
    assert not c.executor.calls and c.control_result["error_code"] == "persistence_failed"


@then("bounded audit records contain correlation, scenario, principal and outcome")
def audit(c):
    records = json.loads((c.control_dir / "state.json").read_text())["audit"]
    assert records and len(records) <= 128
    assert all(
        {"principal", "operation", "request_key", "outcome", "at"} <= set(r) for r in records
    )


@then("no secret or caller command is persisted")
def no_secret(c):
    text = (c.control_dir / "state.json").read_text()
    assert "secret" not in text and "command" not in text


@when("God resets with another fresh request key at verified baseline")
def repeated_baseline(c):
    c.calls_before = list(c.executor.calls)
    c.gen_before = c.topology.inventory["generation"]
    c.second_reset = asyncio.run(c.controller.reset("fresh-reset-key", "god"))


@then("the second reset performs no node mutation and does not advance generation")
def no_baseline_mutation(c):
    assert (
        c.second_reset["error_code"] is None
        and c.executor.calls == c.calls_before
        and c.topology.inventory["generation"] == c.gen_before
    )


@given("a persisted controller state with a malformed audit or invalid generation")
def corrupt_state(c):
    c.control_dir.mkdir(exist_ok=True)
    (c.control_dir / "state.json").write_text(
        '{"state":"baseline","generation":-1,"results":{},"audit":"bad"}'
    )


@then("it reports reconciliation_required with corrupt_state rather than throwing an exception")
def corrupt_state_result(c):
    assert (
        c.controller.get_state()["state"] == "reconciliation_required"
        and c.controller.get_state()["error_code"] == "corrupt_state"
    )


@when("final reset persistence fails after node recovery")
def reset_persist_failure(c):
    original = c.controller.save

    def failing():
        if c.controller.state["state"] == "baseline":
            raise OSError("disk full")
        original()

    with patch.object(c.controller, "save", side_effect=failing):
        c.persist_result = asyncio.run(c.controller.reset("persist-reset-key", "god"))


@then("the response is an error and the publicly visible generation has not advanced")
def persist_failed(c):
    assert c.persist_result["error_code"] and c.topology.inventory["generation"] == 1, (
        c.persist_result
    )


@then("new mutations require reconciliation")
def requires_reconciliation(c):
    assert c.controller.get_state()["state"] == "reconciliation_required"


@then("persisted fault identity is retained but verified is false until explicit recovery")
def restart_not_verified(c):
    state = c.controller.get_state()
    assert (
        state["state"] == "reconciliation_required"
        and state["scenario_id"] == "core-link-failure"
        and state["verified"] is False
    ), state


@when("reset persistence fails between state and generation replacement and further writes fail")
def partial_publication(c):
    import os

    original = os.replace
    failed = False

    def replace(source, target):
        nonlocal failed
        if failed:
            raise OSError("storage unavailable")
        if str(target).endswith("generation.json") and c.controller.state["generation"] == 2:
            failed = True
            raise OSError("generation publication failed")
        return original(source, target)

    with patch("minicore_mcp.faults.os.replace", side_effect=replace):
        c.partial_result = asyncio.run(c.controller.reset("partial-reset-key", "god"))
    assert c.partial_result["error_code"], c.partial_result


@then(
    "restart requires reconciliation at the last committed generation without replaying reset success"
)
def partial_restart(c):
    state = c.controller.get_state()
    assert (
        state["state"] == "reconciliation_required"
        and state["verified"] is False
        and state["generation"] == 1
    ), state
    replay = c.controller.replay("reset", None, "partial-reset-key")
    assert replay is None or replay["error_code"], replay
    assert asyncio.run(c.controller.reset("recover-partial-key", "god"))["data"]["generation"] == 2


@when("a baseline reset result cannot be persisted")
def baseline_persist_failure(c):
    with patch.object(c.controller, "save", side_effect=OSError("disk full")):
        c.baseline_failed = asyncio.run(c.controller.reset("baseline-failed-key", "god"))
    assert c.baseline_failed["error_code"] == "persistence_failed"


@then("retrying that request key must attempt persistence rather than replay uncommitted success")
def no_volatile_replay(c):
    with patch.object(c.controller, "save", side_effect=OSError("disk still full")) as save:
        result = asyncio.run(c.controller.reset("baseline-failed-key", "god"))
    assert save.called and result["error_code"] == "persistence_failed", result


@when("the published generation file disappears")
def missing_generation(c):
    (c.control_dir / "generation.json").unlink()


@then("it exposes no verified baseline and retains no replayable success")
def missing_generation_unverified(c):
    state = c.controller.get_state()
    assert (
        state["state"] == "reconciliation_required"
        and state["verified"] is False
        and not c.controller.state["results"]
    ), state


@when("a God mutation with a known request ID and idempotency key is audited")
def correlated_audit(c):
    from umcp_shared import MCPRequestContext, reset_request_context, set_request_context

    c.server.controller = c.controller
    c.audit_log = []
    context = MCPRequestContext(
        transport="streamable-http",
        request_id="audit-rpc-001",
        principal="god",
        headers={"authorization": "Bearer " + "g" * 40},
    )
    token = set_request_context(context)
    try:
        with patch.object(c.server.logger, "info", side_effect=c.audit_log.append):
            c.audit_response = asyncio.run(
                c.server.handle_tools_call_async(
                    "audit-rpc-001",
                    {
                        "name": "apply_fault",
                        "arguments": {
                            "scenario_id": "core-link-failure",
                            "idempotency_key": "audit-fixed-key",
                        },
                    },
                )
            )
    finally:
        reset_request_context(token)


@then(
    "the completion record contains bounded identity time decision duration generation and fixed target"
)
def correlated_fields(c):
    entries = [json.loads(v) for v in c.audit_log if isinstance(v, str) and v.startswith("{")]
    c.audit_record = next((e for e in entries if e.get("event") == "tool_completed"), None)
    assert c.audit_record is not None, entries
    record = c.audit_record
    assert (
        record["rpc_request_id"] == "audit-rpc-001"
        and record["principal"] == "god"
        and record["mode"] == "god"
    )
    assert (
        record["authorization"] == "allowed"
        and record["tool"] == "apply_fault"
        and record["idempotency_key"] == "audit-fixed-key"
    )
    assert (
        record["target"] == {"node_id": "p1", "interface": "to-p2"} and record["error_code"] is None
    )
    assert (
        record["generation"] == 1
        and record["duration_ms"] >= 0
        and record["at"]
        and record["verified"] is True
    )


@then("the durable controller record matches the same idempotency key without credentials")
def correlate_controller(c):
    assert c.controller.state["audit"][-1]["request_key"] == c.audit_record["idempotency_key"]
    assert "g" * 40 not in json.dumps(c.audit_record) and "authorization: Bearer" not in json.dumps(
        c.audit_record
    )


@when("God supplies an invalid mutation containing credential-shaped arbitrary input")
def invalid_audit(c):
    from umcp_shared import MCPRequestContext, reset_request_context, set_request_context

    c.server.controller = c.controller
    c.audit_log = []
    token = set_request_context(
        MCPRequestContext(
            transport="streamable-http",
            request_id=72,
            principal="god",
            headers={"authorization": "Bearer " + "g" * 40},
        )
    )
    try:
        with patch.object(c.server.logger, "info", side_effect=c.audit_log.append):
            c.audit_response = asyncio.run(
                c.server.handle_tools_call_async(
                    72,
                    {
                        "name": "apply_fault",
                        "arguments": {
                            "scenario_id": "core-link-failure",
                            "idempotency_key": "bad",
                            "arbitrary": "private-secret-value",
                        },
                    },
                )
            )
    finally:
        reset_request_context(token)


@then("audit records invalid_arguments without that input or a node mutation")
def invalid_audit_safe(c):
    entries = [json.loads(v) for v in c.audit_log if isinstance(v, str) and v.startswith("{")]
    record = next((e for e in entries if e.get("event") == "tool_completed"), None)
    assert record and record["error_code"] == "invalid_arguments", entries
    assert (
        not c.executor.calls
        and "private-secret-value" not in json.dumps(entries)
        and "g" * 40 not in json.dumps(entries)
    )
