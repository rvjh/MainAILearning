import asyncio
from typing import Annotated, TypedDict

from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from mcp_client_tools import get_mcp_tools

load_dotenv()


# -----------------------------
# LangGraph State
# -----------------------------

class State(TypedDict):
    messages: Annotated[list, add_messages]


# -----------------------------
# Build Graph
# -----------------------------

async def build_graph():

    # Load tools from MCP server
    tools = await get_mcp_tools()

    print("\nMCP Tools Loaded:")
    for tool in tools:
        print("-", tool.name)

    # LLM
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
    )

    # Attach MCP tools
    llm_with_tools = llm.bind_tools(
        tools,
        tool_choice="auto"
    )


    # Assistant node
    def assistant(state: State):

        response = llm_with_tools.invoke(
            state["messages"]
        )

        # Debug tool calling
        print("\nDEBUG TOOL CALLS:")
        print(response.tool_calls)

        return {
            "messages": [
                response
            ]
        }


    # Create graph
    builder = StateGraph(State)


    builder.add_node(
        "assistant",
        assistant
    )


    builder.add_node(
        "tools",
        ToolNode(tools)
    )


    # Flow:
    #
    # START
    #   |
    # assistant
    #   |
    # tool call?
    #   |
    # tools
    #   |
    # assistant
    #
    #


    builder.add_edge(
        START,
        "assistant"
    )


    builder.add_conditional_edges(
        "assistant",
        tools_condition
    )


    builder.add_edge(
        "tools",
        "assistant"
    )


    graph = builder.compile(
        checkpointer=MemorySaver()
    )


    return graph



# -----------------------------
# Chat Loop
# -----------------------------

async def chat():

    graph = await build_graph()


    config = {
        "configurable": {
            "thread_id": "mcp-agent-demo"
        }
    }


    print("\nType exit to quit\n")


    while True:

        try:
            query = input("You: ")

        except EOFError:
            break


        if query.lower() in [
            "exit",
            "quit"
        ]:
            break


        result = await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content=query
                    )
                ]
            },
            config=config
        )


        print(
            "\nAssistant:",
            result["messages"][-1].content
        )

        print("-" * 60)



if __name__ == "__main__":
    asyncio.run(chat())
