#!/usr/bin/env python3
"""Hygiene lab: redact secrets/PII before export; prompts truncated by policy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from obs_agent.telemetry.redact import redact_payload, redact_text


def main() -> int:
    raw = {
        "question": "My email is owner@example.com and key is sk-abcdefghijklmnopqrstuvwxyz123456",
        "answer": "Contact ssn 123-45-6789 for help.",
        "nested": {"api_key": "api_key=secret-value-here", "ok": True},
        "prompt": "A" * 500,
    }
    cleaned = redact_payload(raw, capture_full_prompts=False)
    print(json.dumps(cleaned, indent=2))

    assert "[REDACTED]" in cleaned["question"]
    assert "[REDACTED]" in cleaned["answer"]
    assert "…" in cleaned["prompt"]
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in json.dumps(cleaned)
    assert "owner@example.com" not in json.dumps(cleaned)

    print("redact_text sample:", redact_text("token sk-abcdefghijklmnopqrstuvwxyz123456"))
    print("hygiene lab: OK")
    print("Also remember: tenant isolation, retention, sampling gaps, exporter failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
