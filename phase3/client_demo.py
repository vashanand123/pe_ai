"""Phase 3 — MCP Client Demo.

Connects to the MCP server we just built, lists its tools, and calls a few.
This is how any MCP-aware app (Claude Code, Cursor, custom) talks to a server.

Make sure the server is running first (in a separate terminal):
    uv run python phase3/server.py

Then run:
    uv run python phase3/client_demo.py
"""

import asyncio
import json
import sys

from fastmcp import Client

sys.stdout.reconfigure(encoding="utf-8")

SERVER_URL = "http://localhost:8000/mcp/"


async def main() -> None:
    async with Client(SERVER_URL) as client:
        tools = await client.list_tools()
        print(f"Connected. Server exposes {len(tools)} tools:")
        for t in tools:
            print(f"  - {t.name}: {t.description.splitlines()[0] if t.description else ''}")

        print("\n" + "=" * 72)
        print("Calling list_funds()")
        print("-" * 72)
        result = await client.call_tool("list_funds", {})
        print(json.dumps(result.data, indent=2))

        print("\n" + "=" * 72)
        print("Calling get_fund_performance(fund_id=1)")
        print("-" * 72)
        result = await client.call_tool("get_fund_performance", {"fund_id": 1})
        print(json.dumps(result.data, indent=2))

        print("\n" + "=" * 72)
        print("Calling run_waterfall_scenario(fund_id=1, hypothetical_total_distributed_musd=540)")
        print("-" * 72)
        result = await client.call_tool(
            "run_waterfall_scenario",
            {"fund_id": 1, "hypothetical_total_distributed_musd": 540.0},
        )
        print(json.dumps(result.data, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
