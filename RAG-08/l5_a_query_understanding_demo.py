"""
============================================================
  LAYER 5: QUERY UNDERSTANDING (LangChain Implementation)
  Agentic AI Enterprise Mastery Bootcamp
============================================================
  WHAT THIS FILE DEMONSTRATES:
    Module 1 — Why raw queries fail (no API key needed)
    Module 2 — Query Reformulation (LangChain ChatOpenAI + prompts)
    Module 3 — Query Expansion (LangChain chains)
    Module 4 — Intent Validation (LangChain structured output)
    Module 5 — Full Layer 5 Pipeline + optional pgvector integration

  INTEGRATION:
    - Schema: l3_prod_setup_notes.md (documents table, embeddings vector(1536))
    - Search: l6_a_access_control_demo.py (query_by_department, pgvector cosine)
    - Layer 5 output feeds into Layer 6 for semantic search when DB available

  HOW TO RUN:
    pip install langchain langchain-openai langchain-core python-dotenv
    python layer5_query_understanding_demo.py

    With real LLM:
    export OPENAI_API_KEY="sk-..."
    python layer5_query_understanding_demo.py

    With pgvector (requires l6 docs loaded):
    python layer5_query_understanding_demo.py --pgvector
============================================================
"""

import json
import math
import os
from typing import Optional
import datetime
from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
# from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq

load_dotenv()

# ─────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────
def _check_pgvector() -> bool:
    import sys
    return "--pgvector" in sys.argv

USE_REAL_LLM = bool(os.getenv("GROQ_API_KEY"))
USE_PGVECTOR = _check_pgvector()

# LangChain LLM (used when GROQ_API_KEY is set)
LLM = ChatGroq(model="openai/gpt-oss-120b", temperature=0) if USE_REAL_LLM else None

# Optional: same config as l6_a_access_control_demo.py (see l3_prod_setup_notes.md)
CONNECTION_STRING = "postgresql://langchain:langchain@localhost:6024/langchain"

print("=" * 60)
print("  LAYER 5: QUERY UNDERSTANDING (LangChain)")
print("  Enterprise RAG — Week 4 Demo")
print("=" * 60)
print(f"  Mode: {'🤖 Real Groq LLM' if USE_REAL_LLM else '🎭 Mock LLM (set GROQ_API_KEY to use real)'}")
print(f"  Search: {'🔗 pgvector (l6 schema)' if USE_PGVECTOR else '📚 In-memory corpus'}")
print("=" * 60)

# ─────────────────────────────────────────────────────────
#  SAMPLE CORPUS  (10 documents — fallback when pgvector unavailable)
# ─────────────────────────────────────────────────────────
CORPUS = [
    {"id": "d1",  "content": "Q4 2024 Financial Report: Company revenue reached $4.2M, up 23% year-over-year. Net profit margin improved to 18%. Customer acquisition cost decreased by 12%."},
    {"id": "d2",  "content": "AWS Cloud Infrastructure Cost Analysis November 2024: EC2 instance costs $0.096/hour for t3.medium. Reserved instances save 40%. Current monthly spend: $45,000."},
    {"id": "d3",  "content": "Employee Handbook: Data retention policy requires all financial records to be stored for 7 years. HR documents retained for 5 years post-employment."},
    {"id": "d4",  "content": "IT Security Policy: All employees must use MFA. Passwords must be 12+ characters. Security incidents must be reported within 24 hours to security@company.com."},
    {"id": "d5",  "content": "Expense Reimbursement Procedure: Submit expenses via Concur within 30 days. Attach receipts for amounts over $25. Manager approval required for items over $500."},
    {"id": "d6",  "content": "Q3 2024 Revenue Review: Q3 revenue was $3.4M. Growth slowed to 15% due to market conditions. Sales pipeline for Q4 looks strong at $8M."},
    {"id": "d7",  "content": "Azure vs AWS Comparison 2024: Azure is 15% cheaper for Windows workloads. AWS has better ML services. Monthly Azure cost estimate: $38,000 vs AWS $45,000."},
    {"id": "d8",  "content": "API Rate Limits Documentation: REST API is rate-limited to 1000 requests/minute. Burst limit: 5000 requests. Exceeding limits returns HTTP 429. Use exponential backoff."},
    {"id": "d9",  "content": "Product Roadmap Q4 2024: Feature X launches November 15. Feature Y enters beta December 1. Mobile app v2.0 release delayed to Q1 2025."},
    {"id": "d10", "content": "Vendor Contract — Acme Corp: Payment terms NET-30. Contract value $250,000 annually. Renewal date January 15, 2025. 60-day termination notice required."},
]

# ─────────────────────────────────────────────────────────
#  MOCK RESPONSES  (when no API key — demo works without)
# ─────────────────────────────────────────────────────────
MOCK_REFORMULATIONS = {
    "rev last q":          "Q4 2024 revenue financial results summary earnings",
    "the aws stuff":       "AWS Amazon Web Services EC2 cloud infrastructure cost pricing",
    "what did we earn":    "company total earnings revenue profit income 2024 financial results",
    "hr policy":           "human resources HR policies procedures employee handbook rules",
    "security issue":      "IT security incident cybersecurity policy response procedure",
    "expense claim":       "expense reimbursement policy submission process procedure Concur",
    "azure or aws":        "AWS versus Azure cloud provider cost comparison 2024 pricing analysis",
    "api limits":          "API rate limiting requests per minute throttling documentation",
    "when feature x":      "product roadmap feature X release launch date Q4 2024 timeline",
    "vendor deal":         "vendor contract Acme Corp payment terms renewal date conditions",
}

MOCK_EXPANSIONS = {
    "Q4 2024 revenue financial results summary earnings": [
        "fourth quarter 2024 revenue profit earnings financial performance",
        "annual financial report 2024 quarterly results income statement",
        "Q4 revenue growth year over year financial summary 2024",
    ],
    "AWS Amazon Web Services EC2 cloud infrastructure cost pricing": [
        "Amazon EC2 instance pricing cloud compute costs November 2024",
        "AWS cloud infrastructure monthly spend budget EC2 t3 reserved",
        "Amazon Web Services cost breakdown instance type pricing 2024",
    ],
    "IT security incident cybersecurity policy response procedure": [
        "information security incident reporting procedure response plan",
        "cybersecurity breach notification policy IT security guidelines",
        "security incident management response escalation IT policy",
    ],
}

MOCK_INTENTS = {
    "Q4 2024 revenue financial results summary earnings":           {"intent": "factual",     "confidence": 0.95, "answerable": True},
    "AWS Amazon Web Services EC2 cloud infrastructure cost pricing": {"intent": "factual",     "confidence": 0.91, "answerable": True},
    "AWS versus Azure comparison":                                   {"intent": "comparative", "confidence": 0.88, "answerable": True},
    "expense reimbursement policy submission process":               {"intent": "procedural",  "confidence": 0.93, "answerable": True},
    "why did costs increase":                                        {"intent": "analytical",  "confidence": 0.82, "answerable": True},
    "what is the weather today":                                     {"intent": "out_of_scope","confidence": 0.97, "answerable": False},
    "tell me a joke":                                                {"intent": "out_of_scope","confidence": 0.99, "answerable": False},
}


# ════════════════════════════════════`══════════════════════
#  LANGCHAIN CHAINS (Query Reformulation, Expansion, Intent)
# ══════════════════════════════════════════════════════════

REFORMULATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", f"Rewrite user queries as clear, specific search queries. Expand abbreviations and informal language. One sentence only, no preamble. Consider the context of today's date {datetime.datetime.now().strftime('%Y-%m-%d')}. This is the date of the query."),
    ("human", "User query: {raw_query}\nRewritten search query:"),
])

EXPAND_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Generate 3 different ways to search for the same information. Use different words but same meaning. One per line, no numbering."),
    ("human", "Original: {query}"),
])

INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Classify search query intent. Types: factual, comparative, procedural, analytical, out_of_scope. Respond with JSON only: {\"intent\": \"...\", \"confidence\": 0.0-1.0, \"answerable\": true/false}"),
    ("human", "Query: {query}"),
])


def _reformulate_with_langchain(raw_query: str) -> str:
    """LangChain chain: raw query → reformulated query."""
    chain = REFORMULATE_PROMPT | LLM | StrOutputParser()
    return chain.invoke({"raw_query": raw_query}).strip()


def _expand_with_langchain(query: str) -> list[str]:
    """LangChain chain: query → list of alternative phrasings."""
    chain = EXPAND_PROMPT | LLM | StrOutputParser()
    raw = chain.invoke({"query": query}).strip()
    return [q.strip() for q in raw.split("\n") if q.strip()][:3]


def _classify_intent_with_langchain(query: str) -> dict:
    """LangChain chain: query → {intent, confidence, answerable}."""
    chain = INTENT_PROMPT | LLM | JsonOutputParser()
    return chain.invoke({"query": query})


# ══════════════════════════════════════════════════════════
#  SEARCH: In-memory keyword similarity OR pgvector (l6 style)
# ══════════════════════════════════════════════════════════

def keyword_similarity(query: str, document: str) -> float:
    """Simple word-overlap similarity for in-memory corpus demo."""
    q_words = set(query.lower().split())
    d_words = set(document.lower().split())
    if not q_words or not d_words:
        return 0.0
    overlap = len(q_words & d_words)
    return overlap / math.sqrt(len(q_words) * len(d_words))


def search_corpus(query: str, top_k: int = 5, department: Optional[str] = None) -> list:
    """
    Search corpus. When USE_PGVECTOR and l6 docs loaded, uses pgvector (l3 schema).
    Otherwise uses in-memory keyword similarity.
    """
    if USE_PGVECTOR:
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from l6_a_access_control_demo import query_by_department
            dept = department or "engineering"
            rows = query_by_department(query, dept, k=top_k)
            return [({"id": f"pg_{i}", "content": content}, sim) for i, (_, content, _, _, _, sim) in enumerate(rows)]
        except Exception as e:
            print(f"  ⚠️ pgvector fallback: {e}")
    # In-memory: filter by department if provided (corpus has no dept, so we ignore)
    scored = [(doc, keyword_similarity(query, doc["content"])) for doc in CORPUS]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


# ══════════════════════════════════════════════════════════
#  MODULE 1: WHY RAW QUERIES FAIL
# ══════════════════════════════════════════════════════════
def module1_raw_query_problems():
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║  MODULE 1: WHY RAW QUERIES FAIL                        ║")
    print("╚" + "═" * 58 + "╝")

    test_cases = [
        {"raw_query": "rev last q",           "target_doc": "d1", "description": "User wants Q4 2024 revenue report"},
        {"raw_query": "the aws stuff",        "target_doc": "d2", "description": "User wants AWS EC2 pricing"},
        {"raw_query": "security issue",       "target_doc": "d4", "description": "User wants IT security incident policy"},
    ]

    for case in test_cases:
        print(f"\n{'─' * 58}")
        print(f"  📝 SCENARIO: {case['description']}")
        print(f"{'─' * 58}")
        print(f"  User types: \"{case['raw_query']}\"")
        print(f"\n  Searching with RAW query...")

        results = search_corpus(case["raw_query"], top_k=5)
        target_rank = None

        print(f"\n  📊 Results (Rank → Document ID → Score):")
        for rank, (doc, score) in enumerate(results, start=1):
            marker = " ← ❌ WRONG" if doc["id"] != case["target_doc"] else " ← ✅ CORRECT"
            is_target = doc["id"] == case["target_doc"]
            if is_target:
                target_rank = rank
            print(f"     Rank {rank}: [{doc['id']}] score={score:.3f}{marker if is_target or rank <= 2 else ''}")
            print(f"            \"{doc['content'][:60]}...\"")

        if target_rank:
            print(f"\n  ⚠️  TARGET document found at rank {target_rank} (not rank 1!)")
        else:
            print(f"\n  ❌  TARGET document NOT in top 5!")

    print(f"\n  {'─' * 58}")
    print(f"  💡 KEY INSIGHT:")
    print(f"     Raw queries use user vocabulary.")
    print(f"     Documents use formal vocabulary.")
    print(f"     Layer 5 bridges this gap BEFORE search happens.")
    print(f"  {'─' * 58}")


# ══════════════════════════════════════════════════════════
#  MODULE 2: QUERY REFORMULATION (LangChain)
# ══════════════════════════════════════════════════════════
def reformulate(raw_query: str) -> str:
    """Reformulate using LangChain or mock."""
    if USE_REAL_LLM and LLM:
        return _reformulate_with_langchain(raw_query)
    return MOCK_REFORMULATIONS.get(raw_query.lower(), raw_query + " detailed information")


def module2_query_reformulation():
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║  MODULE 2: QUERY REFORMULATION (LangChain)             ║")
    print("╚" + "═" * 58 + "╝")

    test_queries = [
        ("rev last q",    "User asking for last quarter revenue"),
        ("the aws stuff", "User asking about AWS costs"),
        ("hr policy",     "User asking about HR policies"),
        ("expense claim", "User asking how to claim expenses"),
    ]

    print(f"\n  HOW REFORMULATION WORKS:")
    print(f"  LangChain chain: REFORMULATE_PROMPT | ChatOpenAI | StrOutputParser")
    print(f"  The LLM expands abbreviations and adds context.")

    for raw, description in test_queries:
        reformulated = reformulate(raw)
        print(f"\n  {'─' * 56}")
        print(f"  📝 Scenario: {description}")
        print(f"     BEFORE: \"{raw}\"")
        print(f"     AFTER:  \"{reformulated}\"")

        raw_results = search_corpus(raw, top_k=3)
        reformed_results = search_corpus(reformulated, top_k=3)

        print(f"\n     Search with RAW query — Top 3:")
        for rank, (doc, score) in enumerate(raw_results, 1):
            print(f"       {rank}. [{doc['id']}] {doc['content'][:55]}...")

        print(f"\n     Search with REFORMULATED query — Top 3:")
        for rank, (doc, score) in enumerate(reformed_results, 1):
            print(f"       {rank}. [{doc['id']}] {doc['content'][:55]}...")

    print(f"\n  {'─' * 56}")
    print(f"  💡 KEY INSIGHT: Reformulation improves precision")
    print(f"     by translating user language → document language.")
    print(f"  {'─' * 56}")


# ══════════════════════════════════════════════════════════
#  MODULE 3: QUERY EXPANSION (LangChain)
# ══════════════════════════════════════════════════════════
def expand_query(query: str) -> list[str]:
    """Expand using LangChain or mock."""
    if USE_REAL_LLM and LLM:
        return _expand_with_langchain(query)
    default = [f"{query} overview details", f"{query} guide summary", f"{query} policy procedure reference"]
    return MOCK_EXPANSIONS.get(query, default)


def module3_query_expansion():
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║  MODULE 3: QUERY EXPANSION (LangChain)                  ║")
    print("╚" + "═" * 58 + "╝")

    base_query = "Q4 2024 revenue financial results summary earnings"
    print(f"\n  PROBLEM: What if the user says 'earnings' but the doc says 'revenue'?")
    print(f"  SOLUTION: LangChain EXPAND_PROMPT | ChatOpenAI → multiple phrasings.")

    print(f"\n  Base query: \"{base_query}\"")
    expansions = expand_query(base_query)

    print(f"\n  Expanded into {len(expansions) + 1} queries:")
    all_queries = [base_query] + expansions
    for i, q in enumerate(all_queries):
        label = "  (original)" if i == 0 else f"  (expansion {i})"
        print(f"    Q{i+1}: \"{q}\" {label}")

    all_doc_ids = set()
    print(f"\n  Documents found per query:")
    for i, q in enumerate(all_queries):
        results = search_corpus(q, top_k=3)
        ids = [r[0]["id"] for r in results]
        all_doc_ids.update(ids)
        print(f"    Q{i+1}: {ids}")

    print(f"\n  Combined unique docs from all queries: {sorted(all_doc_ids)}")
    print(f"  → More coverage = higher recall!")

    print(f"\n  {'─' * 56}")
    print(f"  💡 KEY INSIGHT: Expansion improves recall by ~20%.")
    print(f"     Use RRF (Layer 7) to merge multi-query results.")
    print(f"  {'─' * 56}")


# ══════════════════════════════════════════════════════════
#  MODULE 4: INTENT VALIDATION (LangChain structured output)
# ══════════════════════════════════════════════════════════
def classify_intent(query: str) -> dict:
    """Classify intent using LangChain JsonOutputParser or mock."""
    if USE_REAL_LLM and LLM:
        try:
            return _classify_intent_with_langchain(query)
        except Exception:
            pass
    default = {"intent": "factual", "confidence": 0.75, "answerable": True}
    # Exact or partial match for mock
    q_lower = query.lower()
    for k, v in MOCK_INTENTS.items():
        if q_lower == k.lower() or k.lower() in q_lower or q_lower in k.lower():
            return v
    # Fallbacks for known out-of-scope
    if "weather" in q_lower or "joke" in q_lower:
        return {"intent": "out_of_scope", "confidence": 0.97, "answerable": False}
    return default


def module4_intent_validation():
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║  MODULE 4: INTENT VALIDATION (LangChain JsonOutputParser)║")
    print("╚" + "═" * 58 + "╝")

    INTENT_DESCRIPTIONS = {
        "factual":      "Find a specific fact or figure",
        "comparative":  "Compare two or more things",
        "procedural":   "Step-by-step instructions",
        "analytical":   "Requires reasoning, not just lookup",
        "out_of_scope": "Cannot be answered from documents",
    }

    test_queries = [
        ("Q4 2024 revenue financial results summary earnings",            "What's our Q4 revenue?"),
        ("expense reimbursement policy submission process procedure Concur","How do I submit an expense?"),
        ("what is the weather today",                                     "What is the weather today?"),
        ("tell me a joke",                                                "Tell me a joke"),
        ("why did costs increase",                                        "Why did costs increase?"),
    ]

    print(f"\n  PROBLEM: Some queries can't be answered from your documents.")
    print(f"  SOLUTION: INTENT_PROMPT | ChatOpenAI | JsonOutputParser")

    print(f"\n  {'─' * 56}")
    print(f"  {'Query':<40} {'Intent':<14} {'Answerable':<12} {'Confidence'}")
    print(f"  {'─' * 56}")

    for query, original in test_queries:
        result = classify_intent(query)
        intent = result.get("intent", "unknown")
        answerable = result.get("answerable", True)
        confidence = result.get("confidence", 0.0)
        icon = "✅" if answerable else "❌"
        display_q = original[:38]
        print(f"  {display_q:<40} {intent:<14} {icon} {str(answerable):<10} {confidence:.0%}")

    print(f"\n  Intent descriptions:")
    for intent, desc in INTENT_DESCRIPTIONS.items():
        print(f"    {intent:<15} → {desc}")

    print(f"\n  {'─' * 56}")
    print(f"  💡 KEY INSIGHT: Rejecting out-of-scope queries saves")
    print(f"     vector search resources and prevents hallucination.")
    print(f"  {'─' * 56}")


# ══════════════════════════════════════════════════════════
#  MODULE 5: FULL LAYER 5 PIPELINE (LangChain + optional pgvector)
# ══════════════════════════════════════════════════════════
class QueryUnderstandingLayer:
    """
    Full Layer 5 pipeline using LangChain.
    Output feeds into l6_a_access_control_demo.query_by_department for semantic search
    when documents are stored in pgvector (l3_prod_setup_notes.md schema).
    """

    def process(self, raw_query: str) -> dict:
        reformulated = reformulate(raw_query)
        expansions = expand_query(reformulated)
        all_queries = [reformulated] + expansions[:2]
        intent_result = classify_intent(reformulated)
        return {
            "raw_query":     raw_query,
            "reformulated": reformulated,
            "all_queries":  all_queries,
            "intent":       intent_result["intent"],
            "answerable":   intent_result["answerable"],
            "confidence":   intent_result["confidence"],
        }


def module5_full_pipeline():
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║  MODULE 5: FULL LAYER 5 PIPELINE (LangChain)            ║")
    print("╚" + "═" * 58 + "╝")

    layer5 = QueryUnderstandingLayer()

    test_scenarios = [
        ("rev last q",    "d1",  "Q4 2024 revenue"),
        ("the aws stuff", "d2",  "AWS EC2 pricing"),
        ("expense claim", "d5",  "Expense procedure"),
    ]

    print(f"\n  PRECISION COMPARISON: Raw vs Layer 5 Processed")
    print(f"\n  {'Query':<20} {'Target':<8} {'Raw Rank':<10} {'L5 Rank':<10} {'Improved?'}")
    print(f"  {'─' * 58}")

    for raw, target_id, label in test_scenarios:
        raw_results = search_corpus(raw, top_k=10)
        raw_rank = next((i + 1 for i, (d, _) in enumerate(raw_results) if d["id"] == target_id), 11)

        processed = layer5.process(raw)
        if processed["answerable"]:
            l5_results = search_corpus(processed["reformulated"], top_k=10)
            l5_rank = next((i + 1 for i, (d, _) in enumerate(l5_results) if d["id"] == target_id), 11)
        else:
            l5_rank = 0

        improved = "✅ YES" if l5_rank < raw_rank and l5_rank > 0 else ("🚫 REJECTED" if l5_rank == 0 else "➡️  SAME")
        print(f"  {label:<20} [{target_id}]   {str(raw_rank):<10} {str(l5_rank):<10} {improved}")

    print(f"\n  FULL PIPELINE TRACE (LangChain chains end-to-end):")
    print(f"  {'─' * 58}")
    sample = layer5.process("rev last q")
    print(f"  1. Raw input:      \"{sample['raw_query']}\"")
    print(f"  2. Reformulated:   \"{sample['reformulated']}\"")
    print(f"  3. All queries:    {len(sample['all_queries'])} phrasings")
    for i, q in enumerate(sample["all_queries"]):
        print(f"       Q{i+1}: \"{q[:55]}\"")
    print(f"  4. Intent:         {sample['intent']} (confidence: {sample['confidence']:.0%})")
    print(f"  5. Answerable:     {'YES — proceed to Layer 6 (l6 query_by_department)' if sample['answerable'] else 'NO — return early'}")
    print(f"\n  {'─' * 58}")
    print(f"  💡 INTEGRATION: Layer 5 output → l6.query_by_department(query, dept)")
    print(f"     Schema: l3_prod_setup_notes.md (documents.embedding vector(1536))")
    print(f"  {'─' * 58}")


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    module1_raw_query_problems()
    input("\n  ▶ Press ENTER to run Module 2: Query Reformulation...")

    module2_query_reformulation()
    input("\n  ▶ Press ENTER to run Module 3: Query Expansion...")

    module3_query_expansion()
    input("\n  ▶ Press ENTER to run Module 4: Intent Validation...")

    module4_intent_validation()
    input("\n  ▶ Press ENTER to run Module 5: Full Pipeline...")

    module5_full_pipeline()

    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║  ✅  LAYER 5 DEMO COMPLETE (LangChain)                   ║")
    print("║                                                        ║")
    print("║  KEY TAKEAWAYS:                                        ║")
    print("║   • ChatPromptTemplate | ChatOpenAI | StrOutputParser   ║")
    print("║   • JsonOutputParser for structured intent             ║")
    print("║   • Reformulation + expansion + intent validation       ║")
    print("║   • Feeds into l6 pgvector search (l3 schema)           ║")
    print("╚" + "═" * 58 + "╝")
    print()