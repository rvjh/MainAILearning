import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client, evaluate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")
if not os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGSMITH_API_KEY") == "replace-me":
    raise SystemExit("Set LANGSMITH_API_KEY to publish the dataset.")

client = Client()
name = "support-rag-golden-v1"
existing = list(client.list_datasets(dataset_name=name))
dataset = existing[0] if existing else client.create_dataset(dataset_name=name, description="RAG golden release gate")
known = {e.inputs["case_id"] for e in client.list_examples(dataset_id=dataset.id)}
rows = [json.loads(line) for line in (ROOT / "data/golden.jsonl").read_text().splitlines() if line.strip()]
new_rows = [row for row in rows if row["case_id"] not in known]
if new_rows:
    client.create_examples(dataset_id=dataset.id, examples=[{
        "inputs": {"case_id": row["case_id"], "question": row["question"]},
        "outputs": {"reference_answer": row["reference_answer"], "expected_doc_ids": row["expected_doc_ids"]},
        "metadata": {"split": row["split"], "expected_trajectory": row["expected_trajectory"]},
    } for row in new_rows])
print(f"Dataset ready: {name}; added {len(new_rows)} example(s)")

from evaluated_agent.graph import EvaluatedRAG

app = EvaluatedRAG(ROOT / "data/corpus.json")


def target(inputs: dict) -> dict:
    output = app.invoke(inputs["question"])
    return {
        "answer": output["answer"].answer,
        "citations": output["answer"].citations,
        "abstained": output["answer"].abstained,
        "retrieved_doc_ids": output["retrieved_doc_ids"],
        "trajectory": output["trajectory"],
    }


def retrieval_recall(run, example):
    expected = set((example.outputs or {}).get("expected_doc_ids", []))
    actual = set((run.outputs or {}).get("retrieved_doc_ids", []))
    score = 1.0 if not expected else len(expected & actual) / len(expected)
    return {"key": "retrieval_recall", "score": score}


def trajectory_contract(run, example):
    expected = (example.metadata or {}).get("expected_trajectory", [])
    actual = (run.outputs or {}).get("trajectory", [])
    cursor = iter(actual)
    score = float(all(any(step == wanted for step in cursor) for wanted in expected))
    return {"key": "trajectory_contract", "score": score}


experiment = evaluate(
    target,
    data=name,
    evaluators=[retrieval_recall, trajectory_contract],
    experiment_prefix="evaluated-rag-v2",
    max_concurrency=2,
    metadata={"prompt_version": "v2", "model": os.getenv("OPENAI_CHAT_MODEL")},
)
print("LangSmith experiment:", experiment)
