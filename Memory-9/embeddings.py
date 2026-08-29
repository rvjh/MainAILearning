from __future__ import annotations

import hashlib
import math
import re


TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def estimate_tokens(text: str) -> int:
    # Stable classroom approximation; production code should use the model tokenizer.
    return max(1, len(tokenize(text)))


def embed(text: str, dimensions: int = 64) -> tuple[float, ...]:
    """Deterministic no-network embedding used to teach architecture, not recall quality."""
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return tuple(value / norm for value in vector)


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))

