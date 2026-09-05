import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from evaluated_agent.multi_agent.runner import run

parser = argparse.ArgumentParser()
parser.add_argument("--split", choices=["smoke", "full"], default="smoke")
parser.add_argument("--prompt-version", choices=["v1", "v2"], default="v2")
parser.add_argument("--gate", action="store_true")
args = parser.parse_args()

report = run(ROOT, split=args.split, prompt_version=args.prompt_version)
(ROOT / "reports").mkdir(exist_ok=True)
out = ROOT / "reports/multi_agent_latest.json"
out.write_text(json.dumps(report, indent=2))
print(json.dumps(report["summary"], indent=2))
print("Gate:", "PASS" if report["passed"] else "FAIL")
print("Wrote", out)
if args.gate and not report["passed"]:
    raise SystemExit(1)
