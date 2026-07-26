"""DEMO 4 — A real business agent: ecommerce customer support.

Three business tools, a scoped system prompt, and a fake in-memory
"backend" so you can see state actually change.

The agent reads free-form customer text, picks the right tool, extracts
the parameters, acts, and confirms.

"""
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from common import get_model

# --- a pretend backend, so we can SEE the effect of a tool call -------------
ORDERS = {
    "A12345": {"status": "processing", "total": 49.99, "address": "12 Oak St"},
    "B73973": {"status": "processing", "total": 129.00, "address": "9 Pine Rd"},
    "C55555": {"status": "shipped", "total": 22.50, "address": "3 Elm Ave"},
}


@tool
def cancel_order(order_id: str) -> str:
    """Cancel an order that has not yet shipped. Use the customer's order id."""
    order = ORDERS.get(order_id)
    if not order:
        return f"No order found with id {order_id}."
    if order["status"] == "shipped":
        return f"Order {order_id} has already shipped and cannot be cancelled."
    order["status"] = "cancelled"
    return f"Order {order_id} has been cancelled."


@tool
def issue_refund(order_id: str, reason: str) -> str:
    """Refund a cancelled or delivered order. Requires a short reason."""
    order = ORDERS.get(order_id)
    if not order:
        return f"No order found with id {order_id}."
    order["status"] = "refunded"
    return f"Refunded ${order['total']:.2f} for order {order_id} ({reason})."


@tool
def update_address(order_id: str, new_address: str) -> str:
    """Change the delivery address of an order that has not yet shipped."""
    order = ORDERS.get(order_id)
    if not order:
        return f"No order found with id {order_id}."
    if order["status"] == "shipped":
        return f"Order {order_id} already shipped; address cannot be changed."
    order["address"] = new_address
    return f"Delivery address for {order_id} updated to {new_address}."


TOOLS = [cancel_order, issue_refund, update_address]

SYSTEM = SystemMessage(
    "You are a concise ecommerce customer support agent. "
    "Use the available tools to action the customer's request, then confirm "
    "in one short, friendly sentence. If no tool fits the request, say what "
    "you CAN help with instead of simply refusing."
)


class State(TypedDict):
    messages: Annotated[list, add_messages]


def build_graph():
    model = get_model().bind_tools(TOOLS)

    def assistant(state: State) -> dict:
        return {"messages": [model.invoke([SYSTEM] + state["messages"])]}

    builder = StateGraph(State)
    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", tools_condition)
    builder.add_edge("tools", "assistant")
    return builder.compile(checkpointer=MemorySaver())


TICKETS = [
    "Please cancel my order A12345.",
    "Order #B73973 arrived broken — I'd like my money back.",
    "Can you send C55555 to 77 Maple Lane instead?",
    "Do you sell gift cards?",            # no tool fits — watch it redirect
]


def main() -> None:
    graph = build_graph()

    for i, ticket in enumerate(TICKETS, start=1):
        thread = {"configurable": {"thread_id": f"ticket-{i}"}}
        print(f"\n=== Ticket {i} ===")
        print("customer >", ticket)
        result = graph.invoke({"messages": [HumanMessage(ticket)]}, thread)

        for m in result["messages"]:
            if getattr(m, "tool_calls", None):
                for c in m.tool_calls:
                    print(f"   ⚙  {c['name']}({c['args']})")
            elif m.type == "tool":
                print(f"   →  {m.content}")
        print("agent    >", result["messages"][-1].content)

    print("\n=== Backend state after the run ===")
    for oid, o in ORDERS.items():
        print(f"  {oid}: {o['status']:10} {o['address']}")


if __name__ == "__main__":
    main()