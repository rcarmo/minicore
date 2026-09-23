"""Real fault evidence through official SDK. Keys read from local file, never printed."""

from datetime import timedelta
from uuid import uuid4

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = "http://127.0.0.1:19000"


async def fault_runs(tokens):
    report = []
    async with (
        httpx.AsyncClient(headers={"Authorization": "Bearer " + tokens["god"]}, timeout=120) as gh,
        httpx.AsyncClient(
            headers={"Authorization": "Bearer " + tokens["operator"]}, timeout=120
        ) as oh,
    ):
        async with (
            streamable_http_client(URL + "/mcp", http_client=gh) as (gr, gw, _),
            streamable_http_client(URL + "/mcp", http_client=oh) as (orr, ow, _),
        ):
            async with (
                ClientSession(gr, gw, read_timeout_seconds=timedelta(seconds=120)) as god,
                ClientSession(orr, ow, read_timeout_seconds=timedelta(seconds=120)) as operator,
            ):
                await god.initialize()
                await operator.initialize()
                assert {t.name for t in (await operator.list_tools()).tools} == {
                    "list_nodes",
                    "get_routes",
                    "get_interfaces",
                    "get_neighbors",
                    "ping",
                    "get_evidence",
                }
                denied = await oh.post(
                    URL + "/mcp",
                    headers={"MCP-Protocol-Version": "2025-03-26"},
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "get_fault_state"},
                    },
                )
                assert denied.status_code == 403
                catalogue = await god.call_tool("list_fault_scenarios")
                assert all(s["available"] for s in catalogue.structuredContent["data"]["scenarios"])
                try:
                    for scenario in [
                        "core-link-failure",
                        "customer-bgp-failure",
                        "data-path-degradation",
                    ]:
                        for cycle in [1, 2]:
                            before = (await god.call_tool("get_fault_state")).structuredContent[
                                "generation"
                            ]
                            applied = await god.call_tool(
                                "apply_fault",
                                {"scenario_id": scenario, "idempotency_key": str(uuid4())},
                            )
                            assert not applied.isError, applied
                            assert applied.structuredContent["data"]["state"] == "active"
                            # Only the authorised projection includes controller truth.
                            agent = (await oh.get(URL + "/api/v1/topology")).json()
                            full = (await gh.get(URL + "/api/v1/topology?view=god")).json()
                            assert (
                                "controller" not in agent
                                and full["controller"]["scenario_id"] == scenario
                            )
                            activity = (await oh.get(URL + "/api/v1/activity")).json()
                            assert not activity["active"]
                            target = "p1" if scenario == "core-link-failure" else "ce1"
                            iface = (
                                "to-p2"
                                if scenario == "core-link-failure"
                                else "to-pe1"
                                if scenario == "customer-bgp-failure"
                                else "to-host1"
                            )
                            evidence = await operator.call_tool(
                                "get_interfaces", {"node_id": target, "interface": iface}
                            )
                            assert not evidence.isError, evidence
                            if scenario != "data-path-degradation":
                                assert "UP" not in evidence.structuredContent["data"][0]["flags"]
                            else:
                                probe = await operator.call_tool(
                                    "ping",
                                    {"node_id": "ce1", "destination": "10.200.8.2", "count": 5},
                                )
                                assert not probe.isError, probe
                                values = probe.structuredContent["data"]
                                assert values["received"] > 0 and values["rtt_ms"]["avg"] >= 75, (
                                    values
                                )
                            reset = await god.call_tool(
                                "reset_lab", {"idempotency_key": str(uuid4())}
                            )
                            assert not reset.isError, reset
                            assert (
                                reset.structuredContent["data"]["state"] == "baseline"
                                and reset.structuredContent["generation"] == before + 1
                            )
                            # Baseline verify is server-side; also read no-fault interface observation.
                            restored = await operator.call_tool(
                                "get_interfaces", {"node_id": target, "interface": iface}
                            )
                            assert "UP" in restored.structuredContent["data"][0]["flags"]
                            report.append(
                                {
                                    "scenario": scenario,
                                    "cycle": cycle,
                                    "generation_before": before,
                                    "generation_after": reset.structuredContent["generation"],
                                    "fault_verified": True,
                                    "reset_verified": True,
                                    "probe": values
                                    if scenario == "data-path-degradation"
                                    else None,
                                }
                            )
                finally:
                    # Explicit cleanup even when an assertion failed. Never hide reset failure.
                    state = await god.call_tool("get_fault_state")
                    if state.structuredContent["data"]["state"] != "baseline":
                        cleanup = await god.call_tool(
                            "reset_lab", {"idempotency_key": str(uuid4())}
                        )
                        assert not cleanup.isError, cleanup
    return report
