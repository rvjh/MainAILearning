"""
Shared setup for every demo.

Usage:
    from common import get_model, calculator, show
"""

from __future__ import annotations

import ast
import operator
import os
from getpass import getpass

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_groq import ChatGroq

load_dotenv()

MODEL = os.getenv("MODEL", "llama-3.1-8b-instant")


def ensure_api_key() -> None:
    """Ensure the Groq API key is available."""
    if not os.getenv("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = getpass("Enter GROQ_API_KEY: ")


def get_model(temperature: float = 0.0) -> ChatGroq:
    """Return a Groq chat model."""
    ensure_api_key()

    return ChatGroq(
        model=MODEL,
        temperature=temperature,
    )


# ------------------------------------------------------------------
# Safe calculator
# ------------------------------------------------------------------

_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value

    if isinstance(node, ast.BinOp):
        if type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](
                _eval_node(node.left),
                _eval_node(node.right),
            )

    if isinstance(node, ast.UnaryOp):
        if type(node.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(node.op)](
                _eval_node(node.operand)
            )

    raise ValueError("Only arithmetic expressions are supported.")


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression."""
    tree = ast.parse(expression, mode="eval")
    return str(_eval_node(tree.body))


def show(messages):
    """Pretty print conversation."""
    print("\nConversation:\n")

    for msg in messages:
        print("=" * 60)
        print(msg.type.upper())

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            print("Tool Calls:")
            for call in msg.tool_calls:
                print(f"  {call['name']}({call['args']})")

        if msg.content:
            print(msg.content)

    print("=" * 60)