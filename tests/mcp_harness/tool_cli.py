"""Official-SDK local acceptance client; credential files never reach stdout."""

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[2]


async def main():
    role, tool, arguments = sys.argv[1:]
    assert role in {"operator", "god"}
    token = json.loads((ROOT / "secrets/http/mcp-tokens.json").read_text())[role]
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}, timeout=120) as http:
        async with streamable_http_client("http://127.0.0.1:19000/mcp", http_client=http) as (
            read,
            write,
            _,
        ):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=120)
            ) as client:
                await client.initialize()
                result = await client.call_tool(tool, json.loads(arguments))
                print(json.dumps({"isError": result.isError, "evidence": result.structuredContent}))


if __name__ == "__main__":
    asyncio.run(main())
