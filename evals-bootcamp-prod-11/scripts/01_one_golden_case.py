import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from evaluated_agent.graph import EvaluatedRAG

app = EvaluatedRAG(ROOT / "data/corpus.json")
result = app.invoke("Does Enterprise Priority guarantee resolution within two hours?")
print("Retrieved:", result["retrieved_doc_ids"])
print("Trajectory:", " -> ".join(result["trajectory"]))
print("Answer:", result["answer"].model_dump_json(indent=2))

