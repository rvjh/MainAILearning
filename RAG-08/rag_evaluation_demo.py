"""
============================================================
  RAG EVALUATION FRAMEWORK
  Agentic AI Enterprise Mastery Bootcamp — Week 3, Session 1
============================================================
  WHAT THIS FILE DEMONSTRATES:
    Module 1 — Golden dataset structure + LLM-assisted generation
    Module 2 — Retrieval evaluation (Precision@K, Recall, MRR)
    Module 3 — Generation evaluation (Faithfulness, Relevancy)
    Module 4 — Root-cause diagnostic report
    Module 5 — Full continuous evaluation harness

  HOW TO RUN:
    python rag_evaluation_demo.py     (works without any API key!)

    With real OpenAI (for generation evaluation):
    export OPENAI_API_KEY="sk-..."
    python rag_evaluation_demo.py
============================================================
"""

import os
import json
import math
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

# ── Check real LLM ────────────────────────────────────────
try:
    USE_REAL_LLM = bool(os.getenv("GROQ_API_KEY"))
    LLM = (ChatGroq(model="openai/gpt-oss-120b", temperature=0,)
    if USE_REAL_LLM
    else None
)
except ImportError:
    USE_REAL_LLM = False

print("=" * 62)
print("  RAG EVALUATION FRAMEWORK")
print("  Enterprise RAG — Week 3 Demo")
print("=" * 62)
print(f"  Mode: {'🤖 Real OpenAI' if USE_REAL_LLM else '🎭 Mock LLM (set OPENAI_API_KEY for real)'}")
print("=" * 62)


# ─────────────────────────────────────────────────────────
#  DATA STRUCTURES
# ─────────────────────────────────────────────────────────
@dataclass
class Document:
    id:      str
    content: str
    title:   str

@dataclass
class GoldenItem:
    question:        str
    ground_truth:    str
    relevant_doc_ids: List[str]
    category:        str   # factual | comparative | procedural | analytical | adversarial

@dataclass
class RetrievalResult:
    question:      str
    retrieved_ids: List[str]

@dataclass
class GenerationResult:
    question:    str
    context:     str
    answer:      str
    ground_truth: str


# ─────────────────────────────────────────────────────────
#  CORPUS  (same 10 docs across all demos) # Chunks
# ─────────────────────────────────────────────────────────
CORPUS = [
    Document("D1",  "Q4 2024 Financial Report: Revenue reached $4.2M, up 23% year-over-year. Net profit margin 18%. Customer acquisition cost decreased 12%.",     "Q4 2024 Financial Report"),
    Document("D2",  "AWS EC2 instance pricing November 2024. t3.medium: $0.0416/hour on-demand. Reserved instances save 40%. Monthly EC2 spend: $45,000.",          "AWS EC2 Pricing Nov 2024"),
    Document("D3",  "Employee Expense Policy: Submit via Concur within 30 days. Receipts required over $25. Manager approval over $500. International needs pre-approval.", "Expense Reimbursement Policy"),
    Document("D4",  "Data Retention Policy: Financial records 7 years (SOX). HR documents 5 years post-employment. All data encrypted at rest with access logging.", "Data Retention Policy"),
    Document("D5",  "IT Security Incident Response: Report within 24 hours to security@company.com. Severity 1: immediate executive notification. Post-incident review in 5 days.", "IT Security Incident Response"),
    Document("D6",  "Azure vs AWS Comparison 2024: Azure 15% cheaper for Windows. AWS better for ML workloads. Azure monthly cost $38K vs AWS $45K for equivalent compute.", "Azure vs AWS Comparison"),
    Document("D7",  "API Rate Limiting: REST API limited to 1000 req/min. Burst: 5000 req. HTTP 429 on limit exceeded. Use exponential backoff starting at 1 second.",  "API Rate Limits"),
    Document("D8",  "Q3 2024 Revenue: $3.4M revenue, 15% growth. Q4 pipeline valued at $8M. Operating expenses up 8% due to headcount.",                               "Q3 2024 Revenue Summary"),
    Document("D9",  "Product Roadmap Q4 2024: Feature X launches Nov 15. Feature Y beta Dec 1. Mobile app v2.0 delayed to Q1 2025.",                                   "Product Roadmap Q4 2024"),
    Document("D10", "Vendor Contract Acme Corp: NET-30 payment terms. $250K annually. Renewal Jan 15 2025. 60-day termination notice required.",                        "Vendor Contract — Acme Corp"),
]

# ─────────────────────────────────────────────────────────
#  PRE-BUILT GOLDEN DATASET  (20 items across 5 categories)
# ─────────────────────────────────────────────────────────
GOLDEN_DATASET: List[GoldenItem] = [
    # FACTUAL
    GoldenItem("What was the company revenue in Q4 2024?",                 "$4.2M, up 23% year-over-year",            ["D1"],     "factual"),
    GoldenItem("What is the AWS EC2 t3.medium on-demand hourly price?",    "$0.0416 per hour",                        ["D2"],     "factual"),
    GoldenItem("How long must financial records be retained?",             "7 years per SOX compliance",              ["D4"],     "factual"),
    GoldenItem("What is the API rate limit per minute?",                   "1000 requests per minute",                ["D7"],     "factual"),
    GoldenItem("When does Feature X launch?",                              "November 15, 2024",                       ["D9"],     "factual"),
    GoldenItem("What is the vendor contract renewal date for Acme Corp?",  "January 15, 2025",                        ["D10"],    "factual"),
    # PROCEDURAL
    GoldenItem("How do I submit an expense report?",                       "Submit via Concur within 30 days of purchase, attach receipts over $25, manager approval for items over $500", ["D3"], "procedural"),
    GoldenItem("How long do I have to report a security incident?",        "Within 24 hours to security@company.com", ["D5"],     "procedural"),
    GoldenItem("What should I do when the API returns HTTP 429?",          "Implement exponential backoff starting at 1 second", ["D7"], "procedural"),
    # COMPARATIVE
    GoldenItem("Is Azure or AWS cheaper for our workloads?",               "Azure is 15% cheaper for Windows workloads at $38K/month vs AWS $45K/month", ["D6"], "comparative"),
    GoldenItem("How does Q4 2024 revenue compare to Q3 2024?",             "Q4 was $4.2M (+23% YoY). Q3 was $3.4M (+15%). Q4 growth accelerated.", ["D1","D8"], "comparative"),
    # ANALYTICAL
    GoldenItem("Why might cloud costs be high?",                           "AWS EC2 spend is $45K/month; switching to reserved instances could save 40%; Azure might save 15% on Windows workloads", ["D2","D6"], "analytical"),
    GoldenItem("What financial risks does the Acme contract pose?",        "The contract is $250K annually with NET-30 payment terms and requires 60-day termination notice", ["D10"], "analytical"),
    # ADVERSARIAL (out-of-scope — should NOT be answered from docs)
    GoldenItem("What is the weather in San Francisco?",                    "UNANSWERABLE — not in knowledge base", [],          "adversarial"),
    GoldenItem("Tell me about our competitor's pricing strategy",          "UNANSWERABLE — not in knowledge base", [],          "adversarial"),
    GoldenItem("What is the stock price today?",                           "UNANSWERABLE — not in knowledge base", [],          "adversarial"),
    # MORE FACTUAL
    GoldenItem("What is the Q3 2024 revenue pipeline for Q4?",            "$8M in Q4 sales pipeline",                ["D8"],     "factual"),
    GoldenItem("What expense amount requires manager approval?",           "Expenses over $500",                      ["D3"],     "factual"),
    GoldenItem("What is the net profit margin in Q4 2024?",               "18%",                                     ["D1"],     "factual"),
    GoldenItem("How many days termination notice does Acme contract need?","60 days",                                 ["D10"],    "factual"),
]

# ─────────────────────────────────────────────────────────
#  MOCK RETRIEVAL SYSTEMS  (simulates 3 RAG quality levels)
# ─────────────────────────────────────────────────────────
def simulate_retrieval(question: str, system_quality: str) -> List[str]:
    """Simulate different RAG system qualities."""
    # Find relevant doc IDs for this question
    item = next((g for g in GOLDEN_DATASET if g.question == question), None)
    relevant_ids = item.relevant_doc_ids if item else []

    if not relevant_ids:  # adversarial / unanswerable
        return ["D3", "D7", "D2", "D9", "D5"][:5]

    if system_quality == "naive":
        # Often misses or buries the target
        all_ids = [d.id for d in CORPUS]
        noise   = [i for i in all_ids if i not in relevant_ids]
        r       = relevant_ids[0]
        return [noise[0], noise[1], noise[2], r, noise[3]][:5]  # target at rank 4

    elif system_quality == "semantic":
        noise = [d.id for d in CORPUS if d.id not in relevant_ids]
        if len(relevant_ids) >= 2:
            return [noise[0], relevant_ids[0], relevant_ids[1], noise[1], noise[2]]
        return [noise[0], relevant_ids[0], noise[1], noise[2], noise[3]]

    elif system_quality == "production":
        noise = [d.id for d in CORPUS if d.id not in relevant_ids]
        return (relevant_ids + noise)[:5]  # all relevant ids at the top

    return relevant_ids[:5]


# ─────────────────────────────────────────────────────────
#  METRIC HELPERS  (reused across modules)
# ─────────────────────────────────────────────────────────
def precision_at_k(retrieved: list, relevant: set, k: int) -> float:
    return sum(1 for r in retrieved[:k] if r in relevant) / k if k > 0 else 0.0

def recall_at_k(retrieved: list, relevant: set, k: int) -> float:
    if not relevant:
        return 1.0  # vacuously true (adversarial queries)
    return sum(1 for r in retrieved[:k] if r in relevant) / len(relevant)

def mrr(retrieved: list, relevant: set) -> float:
    return next((1.0/(i+1) for i, r in enumerate(retrieved) if r in relevant), 0.0)


# ══════════════════════════════════════════════════════════
#  MODULE 1: GOLDEN DATASET
# ══════════════════════════════════════════════════════════
def module1_golden_dataset():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 1: THE GOLDEN DATASET                            ║")
    print("╚" + "═" * 60 + "╝")

    print(f"""
  WHAT IS A GOLDEN DATASET?
    A set of (question, ground_truth_answer, relevant_doc_ids) triples
    that represent REAL usage of your system.

    This is your evaluation benchmark — every change to any of
    the 7 layers gets tested against it before shipping.

  OUR GOLDEN DATASET: {len(GOLDEN_DATASET)} questions across 5 categories
""")

    category_counts = {}
    for item in GOLDEN_DATASET:
        category_counts[item.category] = category_counts.get(item.category, 0) + 1

    print(f"  Category breakdown:")
    for cat, count in sorted(category_counts.items()):
        bar = "▓" * count
        desc = {
            "factual":    "Direct lookup — specific number or fact",
            "procedural": "How-to — step-by-step instructions",
            "comparative":"Compare two or more options",
            "analytical": "Requires reasoning across multiple docs",
            "adversarial":"Out-of-scope — should be rejected",
        }.get(cat, "")
        print(f"    {cat:<14} {count:>2}  {bar:<8}  {desc}")

    print(f"\n  SAMPLE GOLDEN ITEMS:\n")
    print(f"  {'Category':<14} {'Question':<45} {'Relevant Docs'}")
    print(f"  {'─' * 80}")
    for item in GOLDEN_DATASET[:8]:
        print(f"  {item.category:<14} {item.question[:43]:<45} {item.relevant_doc_ids}")

    print(f"\n  HOW TO BUILD YOUR OWN (LLM-assisted):")
    print(f"  {'─' * 60}")
    print(f"  Step 1: Sample 1 document chunk at random")
    print(f"  Step 2: Prompt LLM: 'Generate a realistic question")
    print(f"          a user would ask about this text.'")
    print(f"  Step 3: Prompt LLM: 'Answer this using ONLY this text.'")
    print(f"  Step 4: Save (question, answer, source_doc_id) as one golden item")
    print(f"  Step 5: Add 20% adversarial questions (unanswerable)")
    print(f"  Repeat 50-100 times. Takes ~2 hours. Worth every minute.")
    print(f"  {'─' * 60}")
    print(f"  💡 KEY: Build the golden dataset BEFORE you build your RAG system.")
    print(f"     It forces you to think about what 'good' looks like first.")
    print(f"  {'─' * 60}")


# ══════════════════════════════════════════════════════════
#  MODULE 2: RETRIEVAL EVALUATION
# ══════════════════════════════════════════════════════════
def module2_retrieval_evaluation():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 2: RETRIEVAL EVALUATION                          ║")
    print("╚" + "═" * 60 + "╝")

    SYSTEMS = {
        "Naive RAG":      "naive",
        "Semantic RAG":   "semantic",
        "Production RAG": "production",
    }

    # Only evaluate on answerable questions
    eval_items = [g for g in GOLDEN_DATASET if g.category != "adversarial"]
    print(f"\n  Evaluating on {len(eval_items)} answerable questions (excluding adversarial)\n")

    system_scores = {}
    for system_name, quality in SYSTEMS.items():
        p5_scores, r5_scores, mrr_scores = [], [], []

        for item in eval_items:
            retrieved     = simulate_retrieval(item.question, quality)
            relevant_set  = set(item.relevant_doc_ids)

            p5_scores.append(precision_at_k(retrieved, relevant_set, 5))
            r5_scores.append(recall_at_k(retrieved, relevant_set, 5))
            mrr_scores.append(mrr(retrieved, relevant_set))

        system_scores[system_name] = {
            "P@5": sum(p5_scores) / len(p5_scores),
            "R@5": sum(r5_scores) / len(r5_scores),
            "MRR": sum(mrr_scores) / len(mrr_scores),
        }

    print(f"  {'System':<20} {'P@5':<10} {'R@5':<10} {'MRR':<10} {'Overall Bar'}")
    print(f"  {'─' * 65}")
    for system_name, scores in system_scores.items():
        avg = sum(scores.values()) / len(scores)
        bar = "█" * int(avg * 20)
        print(f"  {system_name:<20} {scores['P@5']:.3f}     {scores['R@5']:.3f}     {scores['MRR']:.3f}     {bar}")

    # Per-category breakdown for production system
    print(f"\n  PER-CATEGORY BREAKDOWN (Production RAG):\n")
    print(f"  {'Category':<14} {'N':<4} {'P@5':<8} {'R@5':<8} {'MRR':<8} {'Assessment'}")
    print(f"  {'─' * 65}")

    categories = ["factual", "procedural", "comparative", "analytical"]
    for cat in categories:
        cat_items = [g for g in eval_items if g.category == cat]
        p5s, r5s, mrrs = [], [], []
        for item in cat_items:
            retrieved    = simulate_retrieval(item.question, "production")
            relevant_set = set(item.relevant_doc_ids)
            p5s.append(precision_at_k(retrieved, relevant_set, 5))
            r5s.append(recall_at_k(retrieved, relevant_set, 5))
            mrrs.append(mrr(retrieved, relevant_set))

        avg_p5 = sum(p5s)/len(p5s) if p5s else 0
        avg_r5 = sum(r5s)/len(r5s) if r5s else 0
        avg_mrr = sum(mrrs)/len(mrrs) if mrrs else 0
        assess = "✅ Good" if avg_p5 >= 0.6 else "⚠️  Needs work"
        print(f"  {cat:<14} {len(cat_items):<4} {avg_p5:.3f}    {avg_r5:.3f}    {avg_mrr:.3f}    {assess}")

    print(f"\n  {'─' * 60}")
    print(f"  💡 Run this every time you change a layer. If a category")
    print(f"     score drops after your change, you introduced a regression.")
    print(f"  {'─' * 60}")


# ══════════════════════════════════════════════════════════
#  MODULE 3: GENERATION EVALUATION (RAGAS-style)
# ══════════════════════════════════════════════════════════
def module3_generation_evaluation():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 3: GENERATION EVALUATION (RAGAS-STYLE)          ║")
    print("╚" + "═" * 60 + "╝")

    # Pre-built mock LLM answers (represents what a RAG system would produce)
    MOCK_ANSWERS = {
        "What was the company revenue in Q4 2024?": {
            "good_answer": "Q4 2024 revenue was $4.2M, representing 23% year-over-year growth.",
            "bad_answer":  "Revenue was approximately $5M in Q4 2024.",  # hallucinated!
        },
        "How do I submit an expense report?": {
            "good_answer": "Submit your expense report via Concur within 30 days of purchase. Attach receipts for any amount over $25. Manager approval is required for expenses over $500.",
            "bad_answer":  "Submit expenses within 7 days via the HR portal.",  # wrong details
        },
        "What is the API rate limit per minute?": {
            "good_answer": "The REST API is rate-limited to 1000 requests per minute, with a burst allowance of 5000 requests.",
            "bad_answer":  "The API allows unlimited requests per minute.",  # hallucinated
        },
    }

    def evaluate_faithfulness(answer: str, context: str) -> float:
        """Check if every claim in the answer is supported by the context."""
        if USE_REAL_LLM:
            prompt = f"""Given this context:
{context}

And this answer:
{answer}

Score faithfulness 0.0-1.0: what fraction of answer claims are supported by context?
Reply with a single number only (e.g. 0.85)."""
            response = LLM.invoke(prompt)
            raw = response.content.strip()

            try:
                return float(raw)
            except (ValueError, TypeError):
                return 0.5
        # Mock: check word overlap as proxy
        answer_words = set(answer.lower().split())
        context_words = set(context.lower().split())
        overlap = len(answer_words & context_words) / len(answer_words) if answer_words else 0
        return min(overlap * 1.5, 1.0)  # scale up overlap slightly

    def evaluate_answer_relevancy(answer: str, question: str) -> float:
        """Check if the answer actually addresses the question."""
        if USE_REAL_LLM:
            prompt = f"""Question: {question}
Answer: {answer}
Score answer relevancy 0.0-1.0: how well does the answer address the question?
Reply with a single number only."""
            response = LLM.invoke(prompt)
            raw = response.content.strip()
            try:
                return float(raw)
            except (ValueError, TypeError):
                return 0.5
        # Mock: check question keywords in answer
        q_words = set(question.lower().replace("?","").split())
        a_words = set(answer.lower().split())
        overlap = len(q_words & a_words) / len(q_words) if q_words else 0
        return min(overlap * 2, 1.0)

    print(f"""
  THE 4 RAGAS METRICS (Retrieval Augmented Generation Assessment):
    1. Faithfulness     — Is every claim in the answer supported by retrieved docs?
    2. Answer Relevancy — Does the answer actually address the question?
    3. Context Precision— Are retrieved chunks USEFUL for this question?
    4. Context Recall   — Does context contain ALL info needed for a complete answer?

  We score 0.0 to 1.0. Higher is better. Target: ≥ 0.80 for each metric.
""")

    print(f"  COMPARING GOOD ANSWERS vs HALLUCINATED ANSWERS:\n")
    print(f"  {'Question':<43} {'Answer Type':<14} {'Faithfulness':<14} {'Relevancy'}")
    print(f"  {'─' * 85}")

    for question, answers in MOCK_ANSWERS.items():
        # Get context from the corpus
        context = next((d.content for d in CORPUS if any(kw in d.content.lower() for kw in question.lower().split()[:3])), CORPUS[0].content)

        good_faith = evaluate_faithfulness(answers["good_answer"], context)
        good_relev = evaluate_answer_relevancy(answers["good_answer"], question)
        bad_faith  = evaluate_faithfulness(answers["bad_answer"], context)
        bad_relev  = evaluate_answer_relevancy(answers["bad_answer"], question)

        short_q = question[:41]
        print(f"  {short_q:<43} {'✅ Grounded':<14} {good_faith:<14.2f} {good_relev:.2f}")
        print(f"  {'':43} {'❌ Hallucinated':<14} {bad_faith:<14.2f} {bad_relev:.2f}")
        print()

    print(f"  WHAT LOW SCORES TELL YOU:")
    print(f"  {'─' * 60}")
    metrics_guide = [
        ("Faithfulness < 0.8",      "LLM is hallucinating — fix prompt or reduce context noise"),
        ("Answer Relevancy < 0.8",  "Answers are off-topic — check query understanding (Layer 5)"),
        ("Context Precision < 0.7", "Chunks are noisy — improve chunking (L2) or reranking (L7)"),
        ("Context Recall < 0.7",    "Missing key docs — improve query expansion (L5) or BM25 (L7)"),
    ]
    for metric, diagnosis in metrics_guide:
        print(f"    {metric:<30} → {diagnosis}")
    print(f"  {'─' * 60}")


# ══════════════════════════════════════════════════════════
#  MODULE 4: DIAGNOSTIC REPORT
# ══════════════════════════════════════════════════════════
def module4_diagnostic_report():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 4: DIAGNOSTIC REPORT — ROOT CAUSE ANALYSIS      ║")
    print("╚" + "═" * 60 + "╝")

    # Simulate a system with some known weaknesses
    simulated_scores = {
        "Retrieval P@5":         0.64,
        "Retrieval Recall@5":    0.72,
        "Retrieval MRR":         0.61,
        "Faithfulness":          0.83,
        "Answer Relevancy":      0.79,
        "Context Precision":     0.60,  # LOW
        "Context Recall":        0.58,  # LOW
    }

    THRESHOLDS = {
        "Retrieval P@5":         (0.75, "good"),
        "Retrieval Recall@5":    (0.70, "good"),
        "Retrieval MRR":         (0.70, "warn"),
        "Faithfulness":          (0.80, "good"),
        "Answer Relevancy":      (0.80, "warn"),
        "Context Precision":     (0.70, "below"),
        "Context Recall":        (0.65, "below"),
    }

    ROOT_CAUSE = {
        "Retrieval MRR":      "Best docs exist but are at rank 2-3. Add reranking (Layer 7) or improve query reformulation (Layer 5).",
        "Answer Relevancy":   "Answers partially off-topic. Review Layer 5 query reformulation prompt. Also check LLM system prompt — is it focused?",
        "Context Precision":  "Retrieved chunks contain noise. Investigate: (1) Is chunk size too large? (Layer 2). (2) Are query expansions too broad? (Layer 5). (3) Try adding reranking (Layer 7).",
        "Context Recall":     "Missing key documents. Investigate: (1) Improve query expansion coverage (Layer 5). (2) Check hybrid search BM25 coverage (Layer 7). (3) Review chunking — are some chunks too small?",
    }

    print(f"\n  CURRENT SYSTEM SCORECARD:\n")
    print(f"  {'Metric':<25} {'Score':<10} {'Target':<10} {'Status':<10} {'Trend'}")
    print(f"  {'─' * 65}")

    issues = []
    for metric, score in simulated_scores.items():
        target, status = THRESHOLDS[metric]
        if score >= target:
            status_icon = "✅ PASS"
            trend = "▲"
        elif score >= target * 0.9:
            status_icon = "⚠️  WARN"
            trend = "→"
            issues.append(metric)
        else:
            status_icon = "❌ FAIL"
            trend = "▼"
            issues.append(metric)
        bar = "█" * int(score * 15)
        print(f"  {metric:<25} {score:.3f}     {target:.3f}     {status_icon:<10} {bar}")

    print(f"\n  ROOT CAUSE ANALYSIS:")
    print(f"  {'─' * 60}")
    for metric in issues:
        if metric in ROOT_CAUSE:
            print(f"\n  ❌ ISSUE: {metric} = {simulated_scores[metric]:.3f} (target: {THRESHOLDS[metric][0]:.3f})")
            print(f"     CAUSE & FIX:")
            for line in ROOT_CAUSE[metric].split(". "):
                if line:
                    print(f"       → {line.strip()}.")

    print(f"\n  RECOMMENDED ACTION PLAN:")
    print(f"  {'─' * 60}")
    print(f"  Priority 1: Fix Context Recall (Layer 5 query expansion)")
    print(f"              → Add 2-3 synonym expansions per query")
    print(f"              → Expected improvement: +0.10 to +0.15")
    print(f"  Priority 2: Fix Context Precision (Layer 7 reranking)")
    print(f"              → Add cross-encoder reranking on top 20 results")
    print(f"              → Expected improvement: +0.10 to +0.12")
    print(f"  Priority 3: Fix MRR (Layer 7 RRF weights)")
    print(f"              → Increase BM25 weight for exact-term queries")
    print(f"              → Expected improvement: +0.05 to +0.08")
    print(f"  {'─' * 60}")
    print(f"  💡 ALWAYS fix root causes in order of priority.")
    print(f"     One fix at a time. Re-evaluate after each change.")
    print(f"  {'─' * 60}")


# ══════════════════════════════════════════════════════════
#  MODULE 5: FULL CONTINUOUS EVALUATION HARNESS
# ══════════════════════════════════════════════════════════
def module5_full_harness():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 5: CONTINUOUS EVALUATION HARNESS                 ║")
    print("╚" + "═" * 60 + "╝")

    print(f"""
  THE EVALUATION HARNESS:
    Run this before shipping ANY change to your RAG system.
    Treat it like unit tests — never ship without green scores.

  WHAT THE HARNESS DOES:
    1. Runs all 20 golden queries through your pipeline
    2. Computes retrieval metrics (P@5, R@5, MRR)
    3. Computes generation metrics (Faithfulness, Relevancy)
    4. Compares to your baseline scores
    5. Flags regressions automatically
    6. Outputs a pass/fail decision

  SIMULATING: Comparing Naive vs Production RAG
""")

    eval_items  = [g for g in GOLDEN_DATASET if g.category != "adversarial"]
    adv_items   = [g for g in GOLDEN_DATASET if g.category == "adversarial"]

    def run_full_eval(system_quality: str) -> dict:
        p5s, r5s, mrrs = [], [], []
        adv_rejected   = 0

        for item in eval_items:
            retrieved    = simulate_retrieval(item.question, system_quality)
            relevant_set = set(item.relevant_doc_ids)
            p5s.append(precision_at_k(retrieved, relevant_set, 5))
            r5s.append(recall_at_k(retrieved, relevant_set, 5))
            mrrs.append(mrr(retrieved, relevant_set))

        # Adversarial: production system should return empty/rejection
        for item in adv_items:
            retrieved = simulate_retrieval(item.question, system_quality)
            # In production, these would return [] after intent validation
            adv_rejected += 1 if system_quality == "production" else 0

        # Simulated generation scores
        gen_scores = {
            "naive":      {"faithfulness": 0.68, "answer_relevancy": 0.71, "context_precision": 0.55, "context_recall": 0.52},
            "semantic":   {"faithfulness": 0.78, "answer_relevancy": 0.82, "context_precision": 0.67, "context_recall": 0.68},
            "production": {"faithfulness": 0.91, "answer_relevancy": 0.89, "context_precision": 0.81, "context_recall": 0.84},
        }

        return {
            "retrieval": {
                "P@5": sum(p5s)/len(p5s),
                "R@5": sum(r5s)/len(r5s),
                "MRR": sum(mrrs)/len(mrrs),
            },
            "generation": gen_scores.get(system_quality, {}),
            "adversarial_rejection_rate": adv_rejected / len(adv_items) if adv_items else 0,
        }

    SYSTEMS = {"Naive RAG": "naive", "Semantic RAG": "semantic", "Production RAG": "production"}

    results = {}
    for name, quality in SYSTEMS.items():
        results[name] = run_full_eval(quality)

    # Print full report
    print(f"  {'METRIC':<30} {'Naive RAG':<14} {'Semantic RAG':<14} {'Production RAG'}")
    print(f"  {'─' * 75}")

    def row(label, fn):
        vals = [fn(results[s]) for s in SYSTEMS]
        trend = ["", "▲" if vals[1]>vals[0] else "▼", "▲" if vals[2]>vals[1] else "▼"]
        print(f"  {label:<30} " + "  ".join(f"{v:.3f} {t}" .ljust(12) for v, t in zip(vals, trend)))

    print(f"  --- RETRIEVAL ---")
    row("Precision@5",     lambda r: r["retrieval"]["P@5"])
    row("Recall@5",        lambda r: r["retrieval"]["R@5"])
    row("MRR",             lambda r: r["retrieval"]["MRR"])
    print(f"  --- GENERATION ---")
    row("Faithfulness",    lambda r: r["generation"].get("faithfulness", 0))
    row("Answer Relevancy",lambda r: r["generation"].get("answer_relevancy", 0))
    row("Context Precision",lambda r: r["generation"].get("context_precision", 0))
    row("Context Recall",  lambda r: r["generation"].get("context_recall", 0))
    print(f"  --- SAFETY ---")
    row("Adversarial Rejection Rate", lambda r: r["adversarial_rejection_rate"])

    print(f"\n  PASS/FAIL DECISION (Production RAG vs targets):")
    print(f"  {'─' * 60}")
    prod = results["Production RAG"]
    targets = [
        ("Precision@5",     prod["retrieval"]["P@5"],                        0.75, ""),
        ("Recall@5",        prod["retrieval"]["R@5"],                        0.70, ""),
        ("MRR",             prod["retrieval"]["MRR"],                        0.70, ""),
        ("Faithfulness",    prod["generation"].get("faithfulness",0),        0.80, ""),
        ("Answer Relevancy",prod["generation"].get("answer_relevancy",0),    0.80, ""),
    ]
    all_pass = True
    for metric, score, target, _ in targets:
        passed = score >= target
        all_pass = all_pass and passed
        icon = "✅ PASS" if passed else "❌ FAIL"
        print(f"    {metric:<22} {score:.3f} vs target {target:.2f}  {icon}")

    print(f"\n  {'─' * 60}")
    final = "✅ SYSTEM READY TO SHIP" if all_pass else "❌ DO NOT SHIP — FIX FAILING METRICS FIRST"
    print(f"  FINAL VERDICT: {final}")
    print(f"  {'─' * 60}")
    print(f"\n  💡 WORKFLOW:")
    print(f"     Make a change → Run this harness → Compare to baseline")
    print(f"     Any regression? Roll back or fix before shipping.")
    print(f"     This is your safety net for all 7 layers.")


# ══════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    module1_golden_dataset()
    input("\n  ▶ Press ENTER to run Module 2: Retrieval Evaluation...")

    module2_retrieval_evaluation()
    input("\n  ▶ Press ENTER to run Module 3: Generation Evaluation...")

    module3_generation_evaluation()
    input("\n  ▶ Press ENTER to run Module 4: Diagnostic Report...")

    module4_diagnostic_report()
    input("\n  ▶ Press ENTER to run Module 5: Full Evaluation Harness...")

    module5_full_harness()

    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  ✅  RAG EVALUATION DEMO COMPLETE                        ║")
    print("║                                                          ║")
    print("║  KEY TAKEAWAYS:                                          ║")
    print("║   • Golden dataset = your system's unit tests            ║")
    print("║   • Retrieval metrics: P@K, Recall, MRR                 ║")
    print("║   • Generation metrics: faithfulness, relevancy         ║")
    print("║   • Low score → specific layer → specific fix           ║")
    print("║   • Run harness on EVERY layer change before shipping   ║")
    print("╚" + "═" * 60 + "╝")
    print()