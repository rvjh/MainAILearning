import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient 
from dotenv import load_dotenv
from langchain_groq import ChatGroq
load_dotenv()
import sys

async def main():
    client = MultiServerMCPClient({
        "math": {
            "transport": "stdio",
            "command": "python",
            "args": [r"D:\Mainfold_AI_Bootcamp\Orientation\MainAILearning\Session5\fast_mcp.py"]
        },
        "docs-langchain":{
            "transport": "http",
            "url": "https://docs.langchain.com/mcp"
        }
    })
    
    tools = await client.get_tools()
    print("Tools: ", tools)

    # create a subset with the required tools for that task
    add_tool = tools[0]
    multiply_tool = tools[1]

    subset_tools = [add_tool, multiply_tool]
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
    chain = llm.bind_tools(subset_tools)
    print("********************")
    result = await chain.ainvoke("What is the result of 2 + 3 ?")
    print("Result: ", result)
    print("********************")

if __name__ == "__main__":
    asyncio.run(main())



