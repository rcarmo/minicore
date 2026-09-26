import asyncio
import json
from pathlib import Path

from behave import given, then, when
from mcp_harness.live_faults import fault_runs

ROOT = Path(__file__).resolve().parents[2]


@given("the isolated local lab and separate God and Operator credentials")
def fault_fixture(c):
    c.tokens = json.loads((ROOT / "secrets/http/mcp-tokens.json").read_text())
    assert set(c.tokens) == {"operator", "god"} and c.tokens["operator"] != c.tokens["god"]


@when("the official SDK applies each fixed scenario twice with a reset between runs")
def run_faults(c):
    c.fault_report = asyncio.run(fault_runs(c.tokens))


@then("fault state is verified and Operator evidence exposes the corresponding measured changes")
def verified_faults(c):
    assert len(c.fault_report) == 6 and all(r["fault_verified"] for r in c.fault_report)


@then("every reset restores peerings and bidirectional traffic before advancing generation")
def verified_resets(c):
    assert all(
        r["reset_verified"] and r["generation_after"] == r["generation_before"] + 1
        for r in c.fault_report
    )


@then("Operator cannot discover or invoke controller tools or receive controller ground truth")
def operator_boundary(c):
    from mcp_harness.wire import OPERATOR

    assert len(c.fault_report) == 6
    for row in c.fault_report:
        assert set(row["operator_tools"]) == OPERATOR
        assert row["operator_call_status"] == 403
        assert row["operator_has_controller"] is False


@then("no fault mutation appears in the ordinary agent activity stream")
def mutation_hidden(c):
    assert len(c.fault_report) == 6
    assert all(
        r["apply_activity_events"] > 0 and r["reset_activity_events"] > 0 for r in c.fault_report
    )


@then("a failure cleanup resets the lab rather than leaving a test fault active")
def fault_cleanup(c):
    path = ROOT / "reports/live-faults.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(c.fault_report, indent=2) + "\n")
    assert c.fault_report[-1]["reset_verified"]
