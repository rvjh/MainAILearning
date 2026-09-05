import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--baseline", type=Path, required=True)
parser.add_argument("--candidate", type=Path, required=True)
parser.add_argument("--tolerance", type=float, default=0.05)
args = parser.parse_args()

METRIC_KEYS = [
    "route_pass_rate",
    "tool_pass_rate",
    "trajectory_pass_rate",
    "contract_pass_rate",
    "budget_pass_rate",
    "safety_pass_rate",
    "mean_judge",
    "overall_pass_rate",
]

before = json.loads(args.baseline.read_text())["summary"]
after = json.loads(args.candidate.read_text())["summary"]
regressed = False
for metric in METRIC_KEYS:
    if metric not in after:
        continue
    delta = after[metric] - before.get(metric, 0)
    print(f"{metric:28} {before.get(metric, 0):.3f} -> {after[metric]:.3f} ({delta:+.3f})")
    if delta < -args.tolerance:
        regressed = True
if regressed:
    raise SystemExit(f"Regression larger than {args.tolerance} detected")
print("No material multi-agent regression detected")
