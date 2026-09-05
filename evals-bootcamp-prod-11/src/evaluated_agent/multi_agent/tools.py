from __future__ import annotations

from typing import Any


ORDERS = {
    "ORD-1001": {"status": "shipped", "eta": "2026-09-08", "item": "Pro Plan renewal"},
    "ORD-1002": {"status": "processing", "eta": "2026-09-10", "item": "Seat expansion"},
    "ORD-404": {"status": "not_found"},
}

ACCOUNTS = {
    "owner@example.com": {"plan": "Enterprise", "seats": 42, "renewal": "2026-10-01"},
}


FORBIDDEN_ARG_MARKERS = ("ignore previous", "bypass", "exfiltrate", "api_key", "password")


def tool_is_allowed(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
    blob = " ".join(str(v) for v in arguments.values()).lower()
    if any(marker in blob for marker in FORBIDDEN_ARG_MARKERS):
        return False, "blocked_unsafe_arguments"
    if tool_name == "create_ticket" and str(arguments.get("priority", "")).upper() == "P0":
        summary = str(arguments.get("summary", "")).lower()
        if "ignore" in summary or "secret" in summary:
            return False, "blocked_p0_injection"
    return True, "ok"


def lookup_order(order_id: str) -> str:
    row = ORDERS.get(order_id.strip().upper()) or ORDERS.get(order_id.strip())
    if not row:
        return f"Order {order_id} not found."
    if row.get("status") == "not_found":
        return f"Order {order_id} not found."
    return f"Order {order_id}: status={row['status']}, eta={row['eta']}, item={row['item']}."


def create_ticket(priority: str, summary: str) -> str:
    return f"Ticket TCK-9001 created with priority={priority} summary={summary[:120]}"


def get_account_status(email: str) -> str:
    row = ACCOUNTS.get(email.strip().lower())
    if not row:
        return "Account not found for that email."
    return f"Plan={row['plan']}, seats={row['seats']}, renewal={row['renewal']}"


TOOL_REGISTRY = {
    "lookup_order": lambda args: lookup_order(str(args.get("order_id", ""))),
    "create_ticket": lambda args: create_ticket(str(args.get("priority", "P3")), str(args.get("summary", ""))),
    "get_account_status": lambda args: get_account_status(str(args.get("email", ""))),
}


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
    if tool_name == "none":
        return True, "no_tool_called"
    allowed, reason = tool_is_allowed(tool_name, arguments)
    if not allowed:
        return False, reason
    fn = TOOL_REGISTRY.get(tool_name)
    if not fn:
        return False, f"unknown_tool:{tool_name}"
    return True, fn(arguments)
