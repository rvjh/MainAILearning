from __future__ import annotations

from obs_agent.config import get_settings


def estimate_chat_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    input_per_1m: float | None = None,
    output_per_1m: float | None = None,
) -> float:
    settings = get_settings()
    inp = settings.cost_input_usd_per_1m if input_per_1m is None else input_per_1m
    out = settings.cost_output_usd_per_1m if output_per_1m is None else output_per_1m
    return (prompt_tokens / 1_000_000.0) * inp + (completion_tokens / 1_000_000.0) * out


def estimate_tokens(text: str) -> int:
    """Rough classroom estimator (~4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)
