from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .contracts import CaseResult, GoldenCase
from .evaluators import deterministic_contract, judge_average, llm_judge, ordered_subsequence, retrieval_metrics
from .graph import EvaluatedRAG


THRESHOLDS = {
    "mean_recall": 0.80,
    "mean_mrr": 0.70,
    "deterministic_pass_rate": 1.0,
    "trajectory_pass_rate": 1.0,
    "mean_judge": 0.75,
    "overall_pass_rate": 0.80,
}


def load_cases(path: Path, split: str) -> list[GoldenCase]:
    cases = [GoldenCase.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
    return cases if split == "full" else [case for case in cases if case.split == "smoke"]


def run(root: Path, *, split: str, prompt_version: str = "v2") -> dict:
    app = EvaluatedRAG(root / "data/corpus.json", prompt_version=prompt_version)
    corpus = {row["doc_id"]: row["text"] for row in json.loads((root / "data/corpus.json").read_text())}
    results: list[CaseResult] = []
    for case in load_cases(root / "data/golden.jsonl", split):
        output = app.invoke(case.question)
        answer = output["answer"]
        retrieved = output["retrieved_doc_ids"]
        recall, mrr = retrieval_metrics(retrieved, case.expected_doc_ids)
        deterministic_ok, failures = deterministic_contract(case, answer, retrieved)
        trajectory_ok = ordered_subsequence(output["trajectory"], case.expected_trajectory)
        if not trajectory_ok:
            failures.append("trajectory_mismatch")
        evidence = "\n".join(corpus[doc_id] for doc_id in retrieved)
        verdict = llm_judge(case, answer, evidence)
        judge_score = judge_average(verdict)
        passed = recall >= 0.5 and deterministic_ok and trajectory_ok and judge_score >= 0.75
        results.append(CaseResult(
            case_id=case.case_id, retrieved_doc_ids=retrieved, answer=answer,
            trajectory=output["trajectory"], retrieval_recall_at_k=recall,
            reciprocal_rank=mrr, deterministic_pass=deterministic_ok,
            trajectory_pass=trajectory_ok, judge=verdict, judge_score=judge_score,
            passed=passed, failures=failures,
        ))
    n = len(results)
    summary = {
        "mean_recall": sum(r.retrieval_recall_at_k for r in results) / n,
        "mean_mrr": sum(r.reciprocal_rank for r in results) / n,
        "deterministic_pass_rate": sum(r.deterministic_pass for r in results) / n,
        "trajectory_pass_rate": sum(r.trajectory_pass for r in results) / n,
        "mean_judge": sum(r.judge_score for r in results) / n,
        "overall_pass_rate": sum(r.passed for r in results) / n,
    }
    gates = {name: summary[name] >= target for name, target in THRESHOLDS.items()}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "split": split, "prompt_version": prompt_version,
        "thresholds": THRESHOLDS, "summary": summary, "gates": gates,
        "passed": all(gates.values()), "cases": [r.model_dump() for r in results],
    }

