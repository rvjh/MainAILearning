import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--baseline", type=Path, required=True)
parser.add_argument("--candidate", type=Path, required=True)
args = parser.parse_args()

before = json.loads(args.baseline.read_text())["summary"]
after = json.loads(args.candidate.read_text())["summary"]
regressed = False
for metric in sorted(after):
    delta = after[metric] - before.get(metric, 0)
    print(f"{metric:28} {before.get(metric, 0):.3f} -> {after[metric]:.3f} ({delta:+.3f})")
    if delta < -0.05:
        regressed = True
if regressed:
    raise SystemExit("Regression larger than 0.05 detected")

