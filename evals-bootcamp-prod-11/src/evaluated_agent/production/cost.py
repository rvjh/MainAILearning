from __future__ import annotations

import os


DEFAULT_INPUT_PER_1M = float(os.getenv("COST_INPUT_USD_PER_1M", "0.15"))
DEFAULT_OUTPUT_PER_1M = float(os.getenv("COST_OUTPUT_USD_PER_1M", "0.60"))


def estimate_chat_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    input_per_1m: float | None = None,
    output_per_1m: float | None = None,
) -> float:
    inp = DEFAULT_INPUT_PER_1M if input_per_1m is None else input_per_1m
    out = DEFAULT_OUTPUT_PER_1M if output_per_1m is None else output_per_1m
    return (prompt_tokens / 1_000_000.0) * inp + (completion_tokens / 1_000_000.0) * out


def estimate_embedding_cost_usd(tokens: int, *, per_1m: float | None = None) -> float:
    rate = float(os.getenv("COST_EMBEDDING_USD_PER_1M", "0.02")) if per_1m is None else per_1m
    return (tokens / 1_000_000.0) * rate
