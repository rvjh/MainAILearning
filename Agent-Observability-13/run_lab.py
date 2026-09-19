#!/usr/bin/env python3
"""Classroom lab runner — matches slide commands: python3 run_lab.py 01

Maps lab numbers to scripts/0X_*.py in this folder.
Also: python3 run_lab.py primer  → telemetry intro (run before agent labs)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE / "scripts"

CHOICES: dict[str, str] = {}
for path in sorted(SCRIPTS.glob("0*.py")):
    name = path.name
    if name.startswith("00a_"):
        CHOICES["primer"] = name
        continue
    CHOICES[name[:2]] = name

ALLOWED = set(CHOICES) | {"all", "tests"}


def main(argv: list[str]) -> int:
    arg = argv[1] if len(argv) > 1 else "00"
    if arg not in ALLOWED:
        print("Usage: python3 run_lab.py primer|00|01|02|03|04|05|06|07|all|tests")
        print("Labs:")
        if "primer" in CHOICES:
            print(f"  primer  scripts/{CHOICES['primer']}  (run before agent labs)")
        for num, name in sorted((k, v) for k, v in CHOICES.items() if k != "primer"):
            print(f"  {num}  scripts/{name}")
        return 2

    venv_python = HERE / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(HERE / "src"))

    if arg == "tests":
        cmd = [python, "-m", "pytest", "-q"]
    elif arg == "all":
        cmd = [python, "scripts/run_all_demos.py"]
    else:
        cmd = [python, f"scripts/{CHOICES[arg]}"]

    print(f"RUN  {' '.join(cmd)}", flush=True)
    print(f"CWD  {HERE}", flush=True)
    return subprocess.run(cmd, cwd=HERE, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
