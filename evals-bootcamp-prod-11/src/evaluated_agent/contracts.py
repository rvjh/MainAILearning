from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GroundedAnswer(BaseModel):
    answer: str = Field(description="Answer using only the supplied context")
    citations: list[str] = Field(description="Document IDs that directly support the answer")
    abstained: bool = Field(description="True when the context is insufficient")


class JudgeVerdict(BaseModel):
    correctness: int = Field(ge=1, le=4)
    groundedness: int = Field(ge=1, le=4)
    relevance: int = Field(ge=1, le=4)
    safety: int = Field(ge=1, le=4)
    rationale: str


class GoldenCase(BaseModel):
    case_id: str
    split: Literal["smoke", "full"]
    question: str
    reference_answer: str
    expected_doc_ids: list[str]
    expected_trajectory: list[str]
    must_include: list[str] = []
    must_not_include: list[str] = []
    should_abstain: bool = False


class CaseResult(BaseModel):
    case_id: str
    retrieved_doc_ids: list[str]
    answer: GroundedAnswer
    trajectory: list[str]
    retrieval_recall_at_k: float
    reciprocal_rank: float
    deterministic_pass: bool
    trajectory_pass: bool
    judge: JudgeVerdict
    judge_score: float
    passed: bool
    failures: list[str]

