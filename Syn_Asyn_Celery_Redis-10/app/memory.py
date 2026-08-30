"""Governed memory boundary — Saturday learnings on the Sunday worker path.

Model/agent may propose. Policy decides. Code stores.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db import db_connection
from app.errors import MemoryRejected


PROHIBITED = ("password", "api key", "cvv", "card number", "private key", "access token")
MUTABLE_KEYS = {"account_plan", "refund_status", "order_status", "credit_balance"}


class GovernedMemoryGateway:
    def remember(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str,
        purpose: str,
        subject: str,
        key: str,
        value: str,
        source_kind: str,
        source_id: str,
        evidence_excerpt: str,
        verified: bool,
        confidence: float = 0.9,
        ttl_seconds: int | None = 365 * 24 * 3600,
    ) -> dict[str, Any]:
        text = f"{key} {value}".lower()
        if any(term in text for term in PROHIBITED):
            self._audit(tenant_id, user_id, "write_rejected", "sensitivity_not_allowed:regulated")
            raise MemoryRejected("sensitivity_not_allowed:regulated")
        if not evidence_excerpt.strip() or not source_id.strip():
            self._audit(tenant_id, user_id, "write_rejected", "missing_provenance")
            raise MemoryRejected("missing_provenance")
        if source_kind == "model_inference" and not verified:
            self._audit(tenant_id, user_id, "write_rejected", "unverified_model_inference")
            raise MemoryRejected("unverified_model_inference")
        if key in MUTABLE_KEYS and (source_kind != "system_of_record" or not verified):
            self._audit(tenant_id, user_id, "write_rejected", "mutable_fact_requires_system_of_record")
            raise MemoryRejected("mutable_fact_requires_system_of_record")

        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.now(UTC) + timedelta(seconds=min(ttl_seconds, 300) if key in MUTABLE_KEYS else ttl_seconds)

        normalized = re.sub(r"\s+", " ", value.strip()).casefold()
        with db_connection() as conn:
            with conn.transaction():
                existing = conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE tenant_id=%s AND user_id=%s AND agent_id=%s AND purpose=%s
                      AND subject=%s AND memory_key=%s AND status='active'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (tenant_id, user_id, agent_id, purpose, subject, key),
                ).fetchone()
                if existing and re.sub(r"\s+", " ", existing["value"].strip()).casefold() == normalized:
                    self._audit(tenant_id, user_id, "write_deduplicated", str(existing["memory_id"]))
                    return {"decision": "deduplicated", "memory_id": str(existing["memory_id"]), "value": existing["value"]}

                memory_id = str(uuid.uuid4())
                if existing:
                    conn.execute(
                        "UPDATE memories SET status='superseded' WHERE memory_id=%s",
                        (existing["memory_id"],),
                    )
                conn.execute(
                    """
                    INSERT INTO memories (
                      memory_id, tenant_id, user_id, agent_id, purpose, kind, subject, memory_key,
                      value, source_kind, source_id, evidence_excerpt, verified, confidence,
                      sensitivity, status, expires_at, supersedes_id
                    ) VALUES (%s,%s,%s,%s,%s,'semantic',%s,%s,%s,%s,%s,%s,%s,%s,'personal','active',%s,%s)
                    """,
                    (
                        memory_id,
                        tenant_id,
                        user_id,
                        agent_id,
                        purpose,
                        subject,
                        key,
                        value.strip(),
                        source_kind,
                        source_id,
                        evidence_excerpt,
                        verified,
                        confidence,
                        expires_at,
                        existing["memory_id"] if existing else None,
                    ),
                )
                action = "write_superseded" if existing else "write_stored"
                self._audit(tenant_id, user_id, action, memory_id)
                return {"decision": "stored", "memory_id": memory_id, "value": value.strip(), "superseded": bool(existing)}

    def recall(
        self,
        *,
        tenant_id: str,
        user_id: str,
        agent_id: str,
        purpose: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        # Scope first — never global search then filter.
        with db_connection() as conn:
            rows = conn.execute(
                """
                SELECT memory_id, memory_key, value, confidence, created_at
                FROM memories
                WHERE tenant_id=%s AND user_id=%s AND agent_id=%s AND purpose=%s
                  AND status='active'
                  AND (expires_at IS NULL OR expires_at > now())
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (tenant_id, user_id, agent_id, purpose, limit),
            ).fetchall()
            q = query.casefold()
            scored = []
            for row in rows:
                text = f"{row['memory_key']} {row['value']}".casefold()
                score = 1.0 if any(tok in text for tok in q.split() if len(tok) > 2) else 0.2
                scored.append(
                    {
                        "memory_id": str(row["memory_id"]),
                        "key": row["memory_key"],
                        "value": row["value"],
                        "confidence": row["confidence"],
                        "score": score * float(row["confidence"]),
                    }
                )
            scored.sort(key=lambda item: item["score"], reverse=True)
            self._audit(tenant_id, user_id, "read", f"query={query[:40]} considered={len(rows)} selected={min(limit, len(scored))}")
            return scored[:limit]

    def _audit(self, tenant_id: str, user_id: str, action: str, detail: str) -> None:
        with db_connection() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO memory_audit (action, tenant_id, user_id, detail)
                    VALUES (%s,%s,%s,%s)
                    """,
                    (action, tenant_id, user_id, detail),
                )
