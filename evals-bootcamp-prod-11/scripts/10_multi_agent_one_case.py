import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from evaluated_agent.multi_agent.graph import SupportMultiAgent

app = SupportMultiAgent(ROOT / "data/corpus.json")
question = "What is the status of order ORD-1001?"
result = app.invoke(question)
print("Route:", result["route"], "-", result["route_reason"])
print("Trajectory:", " -> ".join(result["trajectory"]))
print("Tools:", [c.model_dump() for c in result["tool_calls"]])
print("Escalated:", result["escalated"], "Abstained:", result["abstained"])
print("Cost USD (est):", round(result["estimated_cost_usd"], 6))
print("Answer:", result["answer"])
