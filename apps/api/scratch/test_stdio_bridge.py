import asyncio
import os
import sys
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp import ClientSession

async def test_bridge():
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "--directory", "j:/plane/apps/api", "python", "-m", "scripts.plane_stdio_mcp"],
        env=dict(os.environ),
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            init_res = await session.initialize()
            print("Server init:", init_res)
            tools = await session.list_tools()
            print(f"Connected to Plane stdio bridge! Tools count: {len(tools.tools)}")
            for t in tools.tools[:5]:
                print(f" - {t.name}: {t.description[:60]}")

            # Test calling a tool
            res = await session.call_tool("plane_list_workspaces", {})
            print("Tool call result:", res)

if __name__ == "__main__":
    asyncio.run(test_bridge())
