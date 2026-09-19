from __future__ import annotations

import time
from typing import Any, Callable

from obs_agent.catalog import lookup_order_record, policy_text
from obs_agent.contracts import FaultScenario, ToolCallRecord

ALLOWED_TOOLS = frozenset({"lookup_order", "get_policy", "create_ticket"})
FORBIDDEN_ARG_MARKERS = (
    "ignore previous",
    "bypass",
    "exfiltrate",
    "api_key",
    "password",
    "sk-",
)


class ToolGateway:
    """Deny-by-default tool boundary with latency / fault injection for labs."""

    def __init__(
        self,
        *,
        allow_demo_faults: bool = True,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.allow_demo_faults = allow_demo_faults
        self._sleep = sleep_fn or time.sleep
        self.call_count = 0
        self.denials = 0
        self.errors = 0

    def tool_is_allowed(self, name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        if name not in ALLOWED_TOOLS:
            return False, f"unknown_tool:{name}"
        blob = " ".join(str(v) for v in arguments.values()).lower()
        if any(marker in blob for marker in FORBIDDEN_ARG_MARKERS):
            return False, "blocked_unsafe_arguments"
        return True, "ok"

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        scenario: FaultScenario = FaultScenario.NONE,
        attempt: int = 1,
    ) -> ToolCallRecord:
        self.call_count += 1
        started = time.perf_counter()

        if (
            self.allow_demo_faults
            and scenario == FaultScenario.DENIED_TOOL
            and name == "create_ticket"
        ):
            self.denials += 1
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                output="denied:policy_violation",
                ok=False,
                denied=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                attempt=attempt,
            )

        allowed, reason = self.tool_is_allowed(name, arguments)
        if not allowed:
            self.denials += 1
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                output=reason,
                ok=False,
                denied=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                attempt=attempt,
            )

        if (
            self.allow_demo_faults
            and scenario == FaultScenario.SLOW_TOOL
            and name == "lookup_order"
        ):
            self._sleep(0.35)

        if (
            self.allow_demo_faults
            and scenario == FaultScenario.TRANSIENT_TOOL_ERROR
            and name == "lookup_order"
            and attempt == 1
        ):
            self.errors += 1
            self._sleep(0.05)
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                output="transient_timeout",
                ok=False,
                denied=False,
                latency_ms=(time.perf_counter() - started) * 1000,
                attempt=attempt,
            )

        try:
            output = self._dispatch(name, arguments)
            ok = True
        except Exception as exc:  # noqa: BLE001 - convert to tool record
            self.errors += 1
            output = f"tool_error:{exc}"
            ok = False

        latency_ms = (time.perf_counter() - started) * 1000
        if (
            self.allow_demo_faults
            and scenario == FaultScenario.SLOW_TOOL
            and name == "lookup_order"
        ):
            latency_ms = max(latency_ms, 350.0)

        return ToolCallRecord(
            name=name,
            arguments=arguments,
            output=output,
            ok=ok,
            denied=False,
            latency_ms=latency_ms,
            attempt=attempt,
        )

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "lookup_order":
            order_id = str(arguments.get("order_id", "")).strip().upper()
            row = lookup_order_record(order_id)
            if not row:
                return f"Order {order_id} not found."
            return (
                f"Order {order_id}: status={row['status']}, eta={row['eta']}, "
                f"item={row['item']}, carrier={row['carrier']}, tracking={row['tracking']}."
            )
        if name == "get_policy":
            topic = str(arguments.get("topic", "support"))
            return policy_text(topic)
        if name == "create_ticket":
            priority = str(arguments.get("priority", "P3"))
            summary = str(arguments.get("summary", ""))[:120]
            return f"Ticket TCK-9001 created with priority={priority} summary={summary}"
        raise ValueError(f"unknown_tool:{name}")
