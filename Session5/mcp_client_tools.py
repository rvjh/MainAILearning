import sys
from langchain_mcp_adapters.client import MultiServerMCPClient

async def get_mcp_tools():
    client = MultiServerMCPClient(
        {
            "math": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [r"D:\Mainfold_AI_Bootcamp\Orientation\MainAILearning\Session5\fast_mcp.py"],
            },
            "docs-langchain": {
                "transport": "http",
                "url": "https://docs.langchain.com/mcp",
            },
        }
    )

    tools = await client.get_tools()
    return tools
