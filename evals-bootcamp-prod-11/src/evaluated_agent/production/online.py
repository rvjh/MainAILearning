from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class OnlineFeedbackEvent(BaseModel):
    event_id: str
    trace_id: str
    system: Literal["rag", "multi_agent"]
    case_like_question: str
    answer_preview: str
    thumbs: Literal["up", "down", "neutral"] | None = None
    user_comment: str = ""
    auto_labels: dict[str, Any] = Field(default_factory=dict)
    sampled: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def should_sample(trace_id: str, *, rate: float = 0.1) -> bool:
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    digest = hashlib.sha256(trace_id.encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket < rate


def maybe_record_feedback(
    *,
    trace_id: str,
    system: Literal["rag", "multi_agent"],
    question: str,
    answer: str,
    rate: float = 0.1,
    thumbs: Literal["up", "down", "neutral"] | None = None,
    auto_labels: dict[str, Any] | None = None,
) -> OnlineFeedbackEvent | None:
    if not should_sample(trace_id, rate=rate):
        return None
    return OnlineFeedbackEvent(
        event_id=f"fb-{random.randint(100000, 999999)}",
        trace_id=trace_id,
        system=system,
        case_like_question=question[:500],
        answer_preview=answer[:500],
        thumbs=thumbs,
        auto_labels=auto_labels or {},
    )
