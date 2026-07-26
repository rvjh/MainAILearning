"""DEMO 3 — Stop hand-rolling the loop: put tools in a LangGraph.

Demo 2 wrote the "keep calling tools until done" loop by hand.
LangGraph gives you two prebuilt pieces that do it properly:

    ToolNode        -> runs whatever tool calls the model requested
    tools_condition -> routes: tool requested? go to tools : END

Plus a checkpointer, so the agent also REMEMBERS across turns.

"""
from typing import Annotated, TypedDict

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from common import calculator, get_model

TOOLS = [DuckDuckGoSearchRun(), calculator]


class State(TypedDict):
    messages: Annotated[list, add_messages]


def build_graph():
    model = get_model().bind_tools(TOOLS)

    def assistant(state: State) -> dict:
        """The 'brain' node: one model call over the running conversation."""
        return {"messages": [model.invoke(state["messages"])]}

    builder = StateGraph(State)
    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(TOOLS))

    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", tools_condition)  # tools? : END
    builder.add_edge("tools", "assistant")                       # loop back

    return builder.compile(checkpointer=MemorySaver())


def main() -> None:
    graph = build_graph()
    thread = {"configurable": {"thread_id": "demo-3"}}

    print("--- turn 1: needs the calculator ---")
    for chunk in graph.stream(
        {"messages": [HumanMessage("What is 1234 * 5678?")]}, thread
    ):
        for node, update in chunk.items():
            print(f"[{node}] {update['messages'][-1].content[:120]}")

    print("\n--- turn 2: relies on MEMORY of turn 1 ---")
    result = graph.invoke(
        {"messages": [HumanMessage("Now divide that result by 2.")]}, thread
    )
    print("bot >", result["messages"][-1].content)

    # The graph can draw itself — printed straight to your terminal.
    print("\nGraph structure:")
    print(graph.get_graph().draw_ascii())


if __name__ == "__main__":
    main()