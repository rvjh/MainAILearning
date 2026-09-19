#!/usr/bin/env python3
"""Run all classroom demos in order (deterministic sleeps where possible)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Load .env before any demo imports settings.
from obs_agent.config import get_settings, load_env  # noqa: E402

SCRIPTS = [
    "00a_telemetry_primer.py",
    "00_preflight.py",
    "01_opening_demo.py",
    "02_trace_lab.py",
    "03_dashboard_lab.py",
    "04_quality_lab.py",
    "05_cost_lab.py",
    "06_slo_alert_lab.py",
    "07_hygiene_lab.py",
]


def main() -> int:
    env_path = load_env(override=True)
    settings = get_settings(reload=True)
    print("=== Env bootstrap ===")
    print(f"env_file={settings.env_file}")
    print(f"openai_configured={settings.use_llm} model={settings.openai_model}")
    print(
        f"langsmith_tracing={settings.langsmith_tracing} "
        f"project={settings.langsmith_project} "
        f"key_set={bool(settings.langsmith_api_key)}"
    )
    if env_path is None:
        print("WARNING: no .env found — demos will run in deterministic mode", file=sys.stderr)

    here = Path(__file__).resolve().parent
    for name in SCRIPTS:
        print("\n" + "#" * 60)
        print(f"# {name}")
        print("#" * 60)
        try:
            runpy.run_path(str(here / name), run_name="__main__")
        except SystemExit as exc:
            code = 0 if exc.code is None else exc.code
            if code != 0:
                print(f"FAILED: {name} exited with {code}", file=sys.stderr)
                return int(code) if isinstance(code, int) else 1
    print("\nALL DEMOS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
