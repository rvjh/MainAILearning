from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluated_agent.contracts import GoldenCase, GroundedAnswer
from evaluated_agent.evaluators import deterministic_contract, ordered_subsequence, retrieval_metrics


def case(**overrides):
    data = dict(case_id="x", split="smoke", question="q", reference_answer="a",
                expected_doc_ids=["D1"], expected_trajectory=["retrieve", "answer"])
    data.update(overrides)
    return GoldenCase(**data)


def test_retrieval_metrics_reward_early_relevant_document():
    assert retrieval_metrics(["D1", "D2"], ["D1"]) == (1.0, 1.0)
    assert retrieval_metrics(["D2", "D1"], ["D1"]) == (1.0, 0.5)


def test_trajectory_is_ordered_subsequence():
    assert ordered_subsequence(["classify", "retrieve", "answer"], ["retrieve", "answer"])
    assert not ordered_subsequence(["answer", "retrieve"], ["retrieve", "answer"])


def test_citation_must_be_retrieved():
    ok, failures = deterministic_contract(case(), GroundedAnswer(answer="a", citations=["D9"], abstained=False), ["D1"])
    assert not ok and "citation_not_retrieved" in failures

