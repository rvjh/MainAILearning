from __future__ import annotations

import re
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"api[_-]?key\s*[:=]\s*\S+", re.I),
]
PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
]


def redact_text(text: str) -> str:
    out = text or ""
    for pattern in SECRET_PATTERNS + PII_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out


def redact_payload(payload: dict[str, Any], *, capture_full_prompts: bool = False) -> dict[str, Any]:
    """Redact before export. Full prompts only when policy allows."""
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"prompt", "question", "answer", "output", "summary"} and isinstance(value, str):
            if capture_full_prompts:
                cleaned[key] = redact_text(value)
            else:
                cleaned[key] = redact_text(value[:200]) + ("…" if len(value) > 200 else "")
        elif isinstance(value, dict):
            cleaned[key] = redact_payload(value, capture_full_prompts=capture_full_prompts)
        elif isinstance(value, list):
            cleaned[key] = [
                redact_payload(v, capture_full_prompts=capture_full_prompts)
                if isinstance(v, dict)
                else redact_text(str(v))
                if isinstance(v, str)
                else v
                for v in value
            ]
        elif isinstance(value, str):
            cleaned[key] = redact_text(value)
        else:
            cleaned[key] = value
    return cleaned
