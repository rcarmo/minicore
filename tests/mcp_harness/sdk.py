"""Official MCP SDK, client-side dependency only. No uMCP imports."""

import asyncio
import json
from datetime import timedelta

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp_harness.wire import ARGS, GOD, OPERATOR


async def exercise(url, tokens):
    evidence = []
    for role in ["operator", "god"]:
        streams = []

        async def response_hook(response, streams=streams):
            if response.request.method == "GET":
                streams.append(response.status_code)
                print(
                    "SDK SSE",
                    response.status_code,
                    "header_names",
                    [k.decode() for k, v in response.request.headers.raw],
                    "protocol",
                    response.request.headers.get("mcp-protocol-version"),
                    "accept",
                    response.request.headers.get("accept"),
                )

        async with httpx.AsyncClient(
            headers={"Authorization": "Bearer " + tokens[role]},
            timeout=15,
            event_hooks={"response": [response_hook]},
        ) as http:
            async with streamable_http_client(url, http_client=http) as (read, write, get_session):
                async with ClientSession(
                    read, write, read_timeout_seconds=timedelta(seconds=10)
                ) as client:
                    init = await client.initialize()
                    assert init.protocolVersion in {"2025-03-26", "2024-11-05"}
                    sid = get_session()
                    assert sid
                    discovered = await client.list_tools()
                    expected = OPERATOR | GOD if role == "god" else OPERATOR
                    assert {t.name for t in discovered.tools} == expected
                    for tool in discovered.tools:
                        assert tool.inputSchema["additionalProperties"] is False
                    pong = await client.send_ping()
                    assert pong.model_dump(exclude_none=True) == {}
                    for _ in range(20):
                        if streams:
                            break
                        await asyncio.sleep(0.05)
                    assert streams and all(code == 200 for code in streams), streams
                    for name in sorted(OPERATOR):
                        result = await client.call_tool(name, ARGS.get(name, {}))
                        assert result.isError == (name not in {"list_nodes", "get_evidence"})
                        assert result.structuredContent == json.loads(result.content[0].text)
                        evidence.append(
                            {
                                "role": role,
                                "tool": name,
                                "is_error": result.isError,
                                "protocol": init.protocolVersion,
                            }
                        )
        async with httpx.AsyncClient() as check:
            response = await check.post(
                url,
                headers={
                    "Authorization": "Bearer " + tokens[role],
                    "Mcp-Session-Id": sid,
                    "MCP-Protocol-Version": init.protocolVersion,
                },
                json={"jsonrpc": "2.0", "id": 99, "method": "tools/list"},
            )
            assert response.status_code == 404, "SDK did not delete its session"
    return evidence


def run_sdk(url, tokens):
    return asyncio.run(exercise(url, tokens))
