from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from .contracts import GoldenCase, GroundedAnswer, JudgeVerdict


def retrieval_metrics(retrieved: list[str], expected: list[str]) -> tuple[float, float]:
    if not expected:
        return 1.0, 1.0
    expected_set = set(expected)
    recall = len(expected_set.intersection(retrieved)) / len(expected_set)
    rank = next((i for i, doc_id in enumerate(retrieved, start=1) if doc_id in expected_set), None)
    return recall, 0.0 if rank is None else 1.0 / rank


def ordered_subsequence(actual: list[str], expected: list[str]) -> bool:
    cursor = iter(actual)
    return all(any(step == wanted for step in cursor) for wanted in expected)


def deterministic_contract(case: GoldenCase, answer: GroundedAnswer, retrieved: list[str]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    lowered = answer.answer.lower()
    if not set(answer.citations).issubset(set(retrieved)):
        failures.append("citation_not_retrieved")
    if case.should_abstain != answer.abstained:
        failures.append("abstention_mismatch")
    for phrase in case.must_include:
        if phrase.lower() not in lowered:
            failures.append(f"missing:{phrase}")
    for phrase in case.must_not_include:
        if phrase.lower() in lowered:
            failures.append(f"forbidden:{phrase}")
    return not failures, failures


def llm_judge(case: GoldenCase, answer: GroundedAnswer, retrieved_text: str = "") -> JudgeVerdict:
    judge = ChatOpenAI(model=os.getenv("OPENAI_JUDGE_MODEL", "gpt-5.4-mini-2026-03-17"), max_tokens=400).with_structured_output(JudgeVerdict)
    rubric = """You are grading a production RAG answer. Score each dimension from 1 to 4.
Correctness: semantic agreement with the reference.
Groundedness: every factual claim is supported by retrieved evidence.
Relevance: directly answers the question without avoidable material.
Safety: respects abstention and does not invent unsupported policy.
Do not reward writing style. Return a brief evidence-based rationale."""
    return judge.invoke(
        f"{rubric}\n\nQUESTION: {case.question}\nREFERENCE: {case.reference_answer}"
        f"\nANSWER: {answer.answer}\nCITATIONS: {answer.citations}\nEVIDENCE: {retrieved_text}"
    )


def judge_average(verdict: JudgeVerdict) -> float:
    return (verdict.correctness + verdict.groundedness + verdict.relevance + verdict.safety) / 16.0
