from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClassroomSLO:
    """
    At least 99% of eligible accepted jobs should produce a validated result
    within 60 seconds over the measurement window.
    """

    name: str = "validated_result_within_60s"
    target_ratio: float = 0.99
    latency_budget_ms: float = 60_000.0

    def evaluate(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        eligible = [r for r in runs if r.get("eligible", True) and not r.get("cancelled")]
        if not eligible:
            return {
                "slo": self.name,
                "eligible": 0,
                "successes": 0,
                "ratio": 1.0,
                "breached": False,
                "notes": "no_eligible_traffic",
            }
        successes = [
            r
            for r in eligible
            if r.get("validated_success")
            and float(r.get("end_to_end_ms", 0)) <= self.latency_budget_ms
            and not r.get("unresolved")
        ]
        ratio = len(successes) / len(eligible)
        return {
            "slo": self.name,
            "eligible": len(eligible),
            "successes": len(successes),
            "ratio": ratio,
            "breached": ratio < self.target_ratio,
            "error_budget_remaining": max(0.0, ratio - (1 - (1 - self.target_ratio))),
            "notes": (
                "eligible=accepted non-cancelled; success=validated within latency; "
                "unresolved/overdue count against success"
            ),
        }
