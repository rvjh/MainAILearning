"""Ground-truth catalog for the support ops agent demos."""

from __future__ import annotations

from typing import Any


ORDERS: dict[str, dict[str, Any]] = {
    "ORD-1001": {
        "status": "shipped",
        "eta": "2026-09-08",
        "item": "Pro Plan renewal",
        "refundable": False,
        "carrier": "UPS",
        "tracking": "1Z999AA10123456784",
    },
    "ORD-1002": {
        "status": "processing",
        "eta": "2026-09-10",
        "item": "Seat expansion",
        "refundable": True,
        "carrier": None,
        "tracking": None,
    },
    "ORD-1003": {
        "status": "delivered",
        "eta": "2026-09-01",
        "item": "Hardware kit",
        "refundable": True,
        "carrier": "FedEx",
        "tracking": "FX998877",
    },
}

POLICIES: dict[str, str] = {
    "refund": (
        "Refunds are allowed within 14 days of delivery for delivered orders. "
        "Processing orders may be cancelled for a full refund. "
        "Shipped orders cannot be refunded until delivered."
    ),
    "shipping": (
        "Shipped orders include carrier and tracking when available. "
        "ETAs are estimates from the order record only — never invent dates."
    ),
    "support": (
        "Create a ticket for billing disputes or missing packages. "
        "Do not promise same-day replacements."
    ),
}


def lookup_order_record(order_id: str) -> dict[str, Any] | None:
    key = order_id.strip().upper()
    return ORDERS.get(key)


def policy_text(topic: str) -> str:
    return POLICIES.get(topic.strip().lower(), "No policy found for that topic.")


def extract_order_id(question: str) -> str | None:
    tokens = question.replace("#", " ").replace(",", " ").split()
    for token in tokens:
        cleaned = token.strip().upper().rstrip(".,?!")
        if cleaned in ORDERS:
            return cleaned
        if cleaned.startswith("ORD-") and len(cleaned) >= 7:
            return cleaned
    return None
