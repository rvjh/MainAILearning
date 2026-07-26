"""DEMO 5 — When things go wrong: validate, retry, fall back, log.

Three production realities, demonstrated:

    1. TOOL CHOICE      force / block tool use instead of leaving it to chance
    2. FAILING TOOLS    an API that errors must not crash the agent
    3. VALIDATION       check the output shape before you trust it

"""
import random
import time

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from common import calculator, get_model


# --- 2) A deliberately flaky "external API" -------------------------------
@tool
def flaky_inventory(sku: str) -> str:
    """Look up warehouse stock for a SKU. (Simulates an unreliable service.)"""
    if random.random() < 0.6:
        raise ConnectionError("inventory-service timed out")
    return f"SKU {sku}: 42 units in stock"


def call_with_retry(tool_obj, call, attempts: int = 3):
    """Retry a tool with exponential backoff, then fall back gracefully."""
    delay = 0.4
    for attempt in range(1, attempts + 1):
        try:
            return tool_obj.invoke(call)
        except Exception as exc:
            print(f"      attempt {attempt} failed: {exc}")
            if attempt == attempts:
                # FALL BACK: return a useful message instead of crashing.
                return ToolMessage(
                    content="Inventory service unavailable; please try again later.",
                    tool_call_id=call["id"],
                )
            time.sleep(delay)
            delay *= 2


def demo_tool_choice() -> None:
    print("\n=== 1. Tool choice: who decides? ===")
    model = get_model()
    q = [HumanMessage("What is 17 * 23?")]

    auto = model.bind_tools([calculator])                       # model decides
    forced = model.bind_tools([calculator], tool_choice="any")  # must use a tool
    blocked = model.bind_tools([calculator], tool_choice="none")  # may not

    print("  auto    →", auto.invoke(q).tool_calls or "answered directly")
    print("  any     →", forced.invoke(q).tool_calls)
    print("  none    →", (blocked.invoke(q).content or "")[:80])


def demo_retry() -> None:
    print("\n=== 2. A failing tool must not kill the agent ===")
    model = get_model().bind_tools([flaky_inventory])
    messages = [HumanMessage("How many units of SKU-9 do we have?")]

    ai_msg = model.invoke(messages)
    messages.append(ai_msg)

    for call in ai_msg.tool_calls:
        print(f"   ⚙  {call['name']}({call['args']})")
        messages.append(call_with_retry(flaky_inventory, call))

    print("  agent >", model.invoke(messages).content)


class StockCheck(BaseModel):
    """Structured result the rest of our system can rely on."""

    sku: str = Field(description="The SKU that was checked")
    units: int = Field(description="Units currently in stock")
    in_stock: bool = Field(description="True if units > 0")


def demo_validation() -> None:
    print("\n=== 3. Validate the shape before you trust it ===")
    model = get_model().with_structured_output(StockCheck)
    result = model.invoke("SKU-9 has 42 units in the warehouse. Summarise it.")
    print("  parsed object:", result)
    print("  result.units is a real int:", isinstance(result.units, int))


if __name__ == "__main__":
    demo_tool_choice()
    demo_retry()
    demo_validation()
    print(
        "\nTakeaway: validate → retry → fall back → log. "
        "That loop turns random failures into predictable behaviour."
    )