from __future__ import annotations

from obs_agent.quality.validators import check_groundedness


def evaluate_answer(
    *,
    answer: str,
    evidence: list[str],
    mode: str = "deterministic",
) -> tuple[bool, list[str], str]:
    """
    LLM-based evaluators are fallible scoring systems — not ground truth.
    Classroom default is deterministic groundedness; optional LLM judge later.
    """
    ok, failures = check_groundedness(answer=answer, evidence=evidence)
    note = "deterministic_groundedness"
    if mode == "llm":
        # Placeholder for a real LLM judge. Keep deterministic signal authoritative
        # for teaching unless an instructor wires ChatOpenAI here.
        note = "llm_judge_stub_falls_back_to_deterministic"
    return ok, failures, note
