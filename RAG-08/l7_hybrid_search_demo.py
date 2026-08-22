"""
  WHAT THIS FILE DEMONSTRATES:
    Module 1 — Sample corpus setup (what we're searching)
    Module 2 — Pure Vector Search and where it fails
    Module 3 — BM25 Keyword Search and where it shines
    Module 4 — Reciprocal Rank Fusion (merging both lists)
    Module 5 — Side-by-side quality comparison

  HOW TO RUN:
    pip install rank-bm25 numpy
============================================================
"""

import math
import sys
import re
from collections import defaultdict

# ── Check dependencies ────────────────────────────────────
try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    print("⚠️  rank-bm25 not installed. Run: pip install rank-bm25")
    print("   Falling back to built-in TF-IDF implementation.\n")

try:
    import numpy as np
    NP_AVAILABLE = True
except ImportError:
    NP_AVAILABLE = False
    print("⚠️  numpy not installed. Run: pip install numpy")

print("=" * 62)
print("  LAYER 7: HYBRID SEARCH & RERANKING")
print("  Enterprise RAG — Week 3 Demo")
print("=" * 62)


# ─────────────────────────────────────────────────────────
#  DEMO CORPUS  — 12 enterprise documents
# ─────────────────────────────────────────────────────────
DOCUMENTS = [
    {"id": "D01", "title": "AWS EC2 Pricing November 2024",
     "content": "AWS EC2 instance pricing for November 2024. t3.medium costs $0.0416/hour on-demand. Reserved instance pricing for EC2 saves 40% annually. Current company monthly EC2 spend is $45,000."},

    {"id": "D02", "title": "Azure Cost Management 2024",
     "content": "Azure virtual machine pricing for 2024. B2s instance costs $0.0416/hour. Azure Hybrid Benefit reduces Windows VM costs by 40%. Monthly Azure spend estimate: $38,000."},

    {"id": "D03", "title": "Cloud Cost Optimization Guide",
     "content": "Strategies for reducing cloud infrastructure costs. Use reserved instances for predictable workloads. Rightsize VMs based on actual CPU utilization. Estimated 35% savings possible."},

    {"id": "D04", "title": "Q4 2024 Financial Report",
     "content": "Company financial results for Q4 2024. Revenue reached $4.2M, a 23% year-over-year increase. Net profit margin 18%. Customer acquisition cost decreased 12% in Q4 2024."},

    {"id": "D05", "title": "Q3 2024 Revenue Summary",
     "content": "Q3 2024 revenue was $3.4M, representing 15% growth. Sales pipeline for Q4 valued at $8M. Operating expenses increased 8% due to headcount growth."},

    {"id": "D06", "title": "Data Retention Policy",
     "content": "Financial records must be retained for 7 years per SOX compliance. HR documents retained 5 years post-employment. All records stored in encrypted S3 with access logging."},

    {"id": "D07", "title": "IT Security Incident Response",
     "content": "Security incidents must be reported within 24 hours to security@company.com. Severity 1 incidents require immediate executive notification. Post-incident review mandatory within 5 business days."},

    {"id": "D08", "title": "API Rate Limiting Documentation",
     "content": "REST API rate limit is 1000 requests per minute. Burst allowance: 5000 requests. HTTP 429 returned when limit exceeded. Implement exponential backoff starting at 1 second."},

    {"id": "D09", "title": "Employee Expense Policy",
     "content": "Submit expense reports via Concur within 30 days of purchase. Receipts required for amounts over $25. Manager approval needed for expenses over $500. International travel requires pre-approval."},

    {"id": "D10", "title": "Product Roadmap Q4 2024",
     "content": "Feature X launches November 15, 2024. Feature Y enters beta December 1. Mobile app v2.0 release delayed to Q1 2025. API v3 documentation published November 2024."},

    {"id": "D11", "title": "AWS vs Azure Decision Guide",
     "content": "AWS recommended for ML workloads due to SageMaker ecosystem. Azure preferred for Microsoft-stack environments. Cost analysis: AWS $45K/month vs Azure $38K/month for equivalent compute."},

    {"id": "D12", "title": "SLA and Uptime Requirements",
     "content": "Production systems must maintain 99.9% uptime SLA. Planned maintenance windows: Sundays 2-4 AM UTC. P1 incidents require 1-hour resolution. Quarterly SLA review with customers required."},
]

# ─────────────────────────────────────────────────────────
#  MOCK EMBEDDINGS  (reproducible, no API key needed)
#  Real system: replace with actual embedding model calls
# ─────────────────────────────────────────────────────────
def make_mock_embedding(text: str, dims: int = 64) -> list:
    """
    Create a reproducible pseudo-embedding from text.
    In production this would be: openai.embeddings.create(input=text, model="text-embedding-3-small")
    For demo purposes we use a deterministic hash-based vector.
    """
    words = text.lower().split()
    vec = [0.0] * dims
    for i, word in enumerate(words):
        idx = hash(word) % dims
        vec[idx] += 1.0 / (i + 1)
    # Normalize
    magnitude = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / magnitude for v in vec]

# Pre-compute document embeddings
DOC_EMBEDDINGS = {doc["id"]: make_mock_embedding(doc["content"]) for doc in DOCUMENTS}

def cosine_similarity(vec_a: list, vec_b: list) -> float:
    dot   = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


# ─────────────────────────────────────────────────────────
#  BM25 FALLBACK  (when rank-bm25 not installed)
# ─────────────────────────────────────────────────────────
class SimpleBM25:
    """Minimal BM25 implementation — no external dependencies."""
    def __init__(self, corpus: list, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b  = b
        self.corpus = corpus
        self.doc_lengths = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_lengths) / len(corpus) if corpus else 1
        self.tf = []
        self.df = defaultdict(int)
        self.N  = len(corpus)
        for doc in corpus:
            tf_dict = defaultdict(int)
            for term in doc:
                tf_dict[term] += 1
            self.tf.append(tf_dict)
            for term in set(doc):
                self.df[term] += 1

    def get_scores(self, query: list) -> list:
        scores = []
        for i, tf_dict in enumerate(self.tf):
            score = 0.0
            dl = self.doc_lengths[i]
            for term in query:
                if term not in tf_dict:
                    continue
                tf = tf_dict[term]
                df = self.df.get(term, 0)
                idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1)
                tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
                score += idf * tf_norm
            scores.append(score)
        return scores


# ══════════════════════════════════════════════════════════
#  MODULE 1: CORPUS SETUP
# ══════════════════════════════════════════════════════════
def module1_corpus_setup():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 1: DEMO CORPUS (Our Knowledge Base)              ║")
    print("╚" + "═" * 60 + "╝")
    print(f"\n  We have {len(DOCUMENTS)} enterprise documents in our knowledge base:\n")
    for doc in DOCUMENTS:
        print(f"    [{doc['id']}] {doc['title']}")
    print(f"\n  We'll search this corpus with three approaches:")
    print(f"    1. Pure Vector Search (semantic similarity)")
    print(f"    2. BM25 Keyword Search (exact term matching)")
    print(f"    3. Hybrid Search (both combined with RRF)")


# ══════════════════════════════════════════════════════════
#  MODULE 2: VECTOR SEARCH (and its failure cases)
# ══════════════════════════════════════════════════════════
def module2_vector_search():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 2: PURE VECTOR SEARCH — WHERE IT FAILS          ║")
    print("╚" + "═" * 60 + "╝")

    def vector_search(query: str, top_k: int = 5) -> list:
        q_emb = make_mock_embedding(query)
        scored = [(doc, cosine_similarity(q_emb, DOC_EMBEDDINGS[doc["id"]])) for doc in DOCUMENTS]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    test_cases = [
        {
            "query":     "AWS EC2 pricing November 2024",
            "target_id": "D01",
            "why_hard":  "Exact date and product code — hard for embeddings",
        },
        {
            "query":     "API rate limit 1000 requests per minute",
            "target_id": "D08",
            "why_hard":  "Exact number and acronym 'API'",
        },
        {
            "query":     "Feature X launch date",
            "target_id": "D10",
            "why_hard":  "Exact proper noun 'Feature X'",
        },
    ]

    print(f"\n  VECTOR SEARCH: embeds the query → finds semantically similar docs")
    print(f"  FAILS ON: acronyms, exact dates, product codes, specific numbers\n")

    for case in test_cases:
        print(f"  {'─' * 58}")
        print(f"  🔍 Query: \"{case['query']}\"")
        print(f"  💬 Why hard: {case['why_hard']}")
        results = vector_search(case["query"], top_k=5)
        print(f"\n  Results (rank → doc ID → similarity score):")
        target_rank = None
        for rank, (doc, score) in enumerate(results, 1):
            is_target = doc["id"] == case["target_id"]
            if is_target:
                target_rank = rank
            marker = " ← ✅ TARGET" if is_target else ""
            print(f"    Rank {rank}: [{doc['id']}] {score:.4f}  {doc['title'][:40]}{marker}")
        if target_rank:
            if target_rank == 1:
                print(f"\n  ✅ Target at rank 1 — vector search worked here!")
            else:
                print(f"\n  ⚠️  Target at rank {target_rank}, not rank 1")
        else:
            print(f"\n  ❌ Target NOT in top 5 — vector search failed!")

    print(f"\n  {'─' * 58}")
    print(f"  💡 KEY INSIGHT: Vector search handles MEANING but struggles")
    print(f"     with EXACT TERMS like acronyms, numbers, and proper nouns.")
    print(f"  {'─' * 58}")


# ══════════════════════════════════════════════════════════
#  MODULE 3: BM25 KEYWORD SEARCH
# ══════════════════════════════════════════════════════════
def module3_bm25_search():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 3: BM25 KEYWORD SEARCH — THE COMPLEMENT         ║")
    print("╚" + "═" * 60 + "╝")

    # Tokenise corpus
    tokenised_corpus = [re.findall(r'\w+', doc["content"].lower()) for doc in DOCUMENTS]
    if BM25_AVAILABLE:
        bm25 = BM25Okapi(tokenised_corpus)
        print(f"\n  Using rank-bm25 library (BM25Okapi implementation)")
    else:
        bm25 = SimpleBM25(tokenised_corpus)
        print(f"\n  Using built-in BM25 implementation")

    def bm25_search(query: str, top_k: int = 5) -> list:
        tokens = re.findall(r'\w+', query.lower())
        scores = bm25.get_scores(tokens)
        ranked = sorted(range(len(DOCUMENTS)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(DOCUMENTS[i], scores[i]) for i in ranked]

    print(f"\n  HOW BM25 WORKS:")
    print(f"    • Tokenises query and documents into words")
    print(f"    • TF (term frequency): rewards docs with more query words")
    print(f"    • IDF (inverse doc freq): rare words matter more")
    print(f"    • BM25 = TF × IDF with length normalisation")

    test_cases = [
        ("AWS EC2 pricing November 2024", "D01"),
        ("API rate limit 1000 requests per minute", "D08"),
        ("Feature X launch date", "D10"),
    ]

    print(f"\n  SAME QUERIES that failed vector search:")
    for query, target_id in test_cases:
        print(f"\n  {'─' * 58}")
        print(f"  🔍 Query: \"{query}\"")
        results = bm25_search(query, top_k=5)
        target_rank = None
        for rank, (doc, score) in enumerate(results, 1):
            is_target = doc["id"] == target_id
            if is_target:
                target_rank = rank
            marker = " ← ✅ TARGET" if is_target else ""
            print(f"    Rank {rank}: [{doc['id']}] score={score:.3f}  {doc['title'][:38]}{marker}")
        if target_rank == 1:
            print(f"  ✅ BM25 finds it at rank 1!")
        elif target_rank:
            print(f"  ✅ BM25 finds it at rank {target_rank}")
        else:
            print(f"  ❌ BM25 did not find it in top 5")

    print(f"\n  {'─' * 58}")
    print(f"  💡 KEY INSIGHT: BM25 handles exact terms (acronyms, numbers)")
    print(f"     but misses semantic meaning. It's the COMPLEMENT of vectors.")
    print(f"  {'─' * 58}")

    return bm25_search   # Return for use in Module 4


# ══════════════════════════════════════════════════════════
#  MODULE 4: RECIPROCAL RANK FUSION (RRF)
# ══════════════════════════════════════════════════════════
def module4_rrf_hybrid(bm25_search_fn=None):
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 4: RRF — MERGING VECTOR + BM25                  ║")
    print("╚" + "═" * 60 + "╝")

    # Re-create bm25 if not passed in
    if bm25_search_fn is None:
        tokenised_corpus = [re.findall(r'\w+', doc["content"].lower()) for doc in DOCUMENTS]
        bm25 = BM25Okapi(tokenised_corpus) if BM25_AVAILABLE else SimpleBM25(tokenised_corpus)
        def bm25_search_fn(query, top_k=5):
            tokens = re.findall(r'\w+', query.lower())
            scores = bm25.get_scores(tokens)
            ranked = sorted(range(len(DOCUMENTS)), key=lambda i: scores[i], reverse=True)[:top_k]
            return [(DOCUMENTS[i], scores[i]) for i in ranked]

    def vector_search(query, top_k=5):
        q_emb = make_mock_embedding(query)
        scored = [(doc, cosine_similarity(q_emb, DOC_EMBEDDINGS[doc["id"]])) for doc in DOCUMENTS]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def reciprocal_rank_fusion(result_lists: list, k: int = 60) -> list:
        """
        RRF: score = Σ 1/(rank + k)  for each ranked list
        k=60 is the standard constant (proven in research to work well)
        """
        doc_scores = {}
        for result_list in result_lists:
            for rank, (doc, _) in enumerate(result_list, start=1):
                doc_id = doc["id"]
                rrf_score = 1.0 / (rank + k)
                if doc_id in doc_scores:
                    doc_scores[doc_id]["score"] += rrf_score
                    doc_scores[doc_id]["ranks"].append(rank)
                else:
                    doc_scores[doc_id] = {"doc": doc, "score": rrf_score, "ranks": [rank]}
        sorted_docs = sorted(doc_scores.values(), key=lambda x: x["score"], reverse=True)
        return sorted_docs

    print(f"\n  HOW RRF WORKS:")
    print(f"    Problem: vector scores and BM25 scores use different scales.")
    print(f"    Solution: convert both lists to RANKS, then apply formula:")
    print(f"    RRF score = 1/(rank + 60)  for each list")
    print(f"    Documents appearing high in BOTH lists get the highest score.")

    # Walk through RRF step-by-step on one query
    demo_query = "AWS EC2 pricing November 2024"
    print(f"\n  STEP-BY-STEP RRF TRACE:")
    print(f"  Query: \"{demo_query}\"\n")

    v_results  = vector_search(demo_query, top_k=6)
    b_results  = bm25_search_fn(demo_query, top_k=6)

    print(f"  {'─' * 58}")
    print(f"  {'Vector Search Results':<30} {'BM25 Results':<30}")
    print(f"  {'─' * 58}")
    for i in range(min(5, len(v_results), len(b_results))):
        v_doc, v_sc = v_results[i]
        b_doc, b_sc = b_results[i]
        v_rrf = round(1/(i+1+60), 5)
        b_rrf = round(1/(i+1+60), 5)
        print(f"  Rank {i+1}: [{v_doc['id']}] v={v_sc:.3f} rrf={v_rrf}  |  [{b_doc['id']}] bm25={b_sc:.2f} rrf={b_rrf}")

    rrf_results = reciprocal_rank_fusion([v_results, b_results])

    print(f"\n  RRF MERGED RESULTS (sum of ranks from both lists):")
    for rank, item in enumerate(rrf_results[:5], 1):
        ranks_str = f"vec_rank={item['ranks'][0]}, bm25_rank={item['ranks'][1] if len(item['ranks']) > 1 else 'not in list'}"
        print(f"    Rank {rank}: [{item['doc']['id']}] RRF={item['score']:.5f}  {item['doc']['title'][:35]}")
        print(f"             ({ranks_str})")

    # Now test all three problematic queries
    print(f"\n  HYBRID SEARCH ON ALL TEST QUERIES:")
    test_cases = [
        ("AWS EC2 pricing November 2024",          "D01"),
        ("API rate limit 1000 requests per minute","D08"),
        ("Feature X launch date",                  "D10"),
    ]

    for query, target_id in test_cases:
        v_res  = vector_search(query, top_k=10)
        b_res  = bm25_search_fn(query, top_k=10)
        hybrid = reciprocal_rank_fusion([v_res, b_res])

        v_rank = next((i+1 for i, (d, _) in enumerate(v_res)  if d["id"] == target_id), 99)
        b_rank = next((i+1 for i, (d, _) in enumerate(b_res)  if d["id"] == target_id), 99)
        h_rank = next((i+1 for i, item   in enumerate(hybrid) if item["doc"]["id"] == target_id), 99)

        print(f"\n  Query: \"{query[:50]}\"")
        print(f"    Vector rank: {v_rank:>3}  |  BM25 rank: {b_rank:>3}  |  Hybrid rank: {h_rank:>3}  {'✅ Best!' if h_rank <= min(v_rank, b_rank) else '→ Combined'}")

    print(f"\n  {'─' * 58}")
    print(f"  💡 KEY INSIGHT: Hybrid wins because it combines the strengths")
    print(f"     of both. Documents good in EITHER list get promoted.")
    print(f"  {'─' * 58}")


# ══════════════════════════════════════════════════════════
#  MODULE 5: FULL COMPARISON REPORT
# ══════════════════════════════════════════════════════════
def module5_comparison_report():
    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  MODULE 5: FULL COMPARISON REPORT                       ║")
    print("╚" + "═" * 60 + "╝")

    # Simulated precision@5 based on realistic benchmarks
    BENCHMARK = {
        "Pure Vector Search":    {"precision_at_5": 0.68, "latency_ms": 50,  "best_for": "Semantic queries"},
        "BM25 Only":             {"precision_at_5": 0.61, "latency_ms": 20,  "best_for": "Exact term queries"},
        "Hybrid (Vector+BM25)":  {"precision_at_5": 0.76, "latency_ms": 100, "best_for": "✅ Production default"},
        "Hybrid + Reranking":    {"precision_at_5": 0.84, "latency_ms": 200, "best_for": "High-stakes queries"},
    }

    print(f"\n  PERFORMANCE BENCHMARK SUMMARY:\n")
    print(f"  {'Approach':<28} {'Precision@5':<14} {'Latency P95':<14} {'Best For'}")
    print(f"  {'─' * 75}")
    for approach, metrics in BENCHMARK.items():
        bar = "█" * int(metrics["precision_at_5"] * 20)
        print(f"  {approach:<28} {metrics['precision_at_5']:.0%} {bar:<12} {metrics['latency_ms']:>5}ms     {metrics['best_for']}")

    print(f"\n  WHICH ONE SHOULD YOU USE?")
    print(f"  {'─' * 58}")
    print(f"  • Internal tool, low stakes?    → Hybrid (Vector+BM25)")
    print(f"  • Legal / financial decisions?  → Hybrid + Reranking")
    print(f"  • High query volume (>1000 QPS)?→ Tune hybrid weights first")
    print(f"  • Mostly natural language?      → Vector weight 0.7, BM25 0.3")
    print(f"  • Lots of acronyms/product IDs? → Vector weight 0.4, BM25 0.6")

    print(f"\n  QUERY TYPE ANALYSIS:")
    print(f"  {'─' * 58}")
    query_types = [
        ("Semantic / conceptual",     "High", "Low",  "Vector wins"),
        ("Exact acronyms (AWS, EC2)", "Low",  "High", "BM25 wins"),
        ("Specific dates/numbers",    "Low",  "High", "BM25 wins"),
        ("Mixed (most real queries)", "Med",  "Med",  "Hybrid wins"),
    ]
    print(f"  {'Query Type':<30} {'Vector':<8} {'BM25':<8} {'Winner'}")
    print(f"  {'─' * 58}")
    for qt, vs, bs, winner in query_types:
        print(f"  {qt:<30} {vs:<8} {bs:<8} {winner}")

    print(f"\n  {'─' * 58}")
    print(f"  💡 PRODUCTION RECOMMENDATION:")
    print(f"     Start with Hybrid (Vector + BM25 + RRF).")
    print(f"     Add reranking only if latency budget allows (+100ms)")
    print(f"     and precision gain justifies the cost.")
    print(f"  {'─' * 58}")


# ══════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    module1_corpus_setup()
    input("\n  ▶ Press ENTER to run Module 2: Vector Search failures...")

    module2_vector_search()
    input("\n  ▶ Press ENTER to run Module 3: BM25 Search...")

    bm25_fn = module3_bm25_search()
    input("\n  ▶ Press ENTER to run Module 4: RRF Hybrid Search...")

    module4_rrf_hybrid(bm25_fn)
    input("\n  ▶ Press ENTER to run Module 5: Full Comparison Report...")

    module5_comparison_report()

    print("\n")
    print("╔" + "═" * 60 + "╗")
    print("║  ✅  LAYER 7 DEMO COMPLETE                               ║")
    print("║                                                          ║")
    print("║  KEY TAKEAWAYS:                                          ║")
    print("║   • Vector search = semantic meaning                     ║")
    print("║   • BM25 = exact keyword matching                        ║")
    print("║   • They fail on different query types                   ║")
    print("║   • RRF merges them using rank position (not raw score)  ║")
    print("║   • Hybrid: 68% → 76% precision. Rerank: → 84%          ║")
    print("╚" + "═" * 60 + "╝")
    print()