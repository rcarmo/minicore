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
