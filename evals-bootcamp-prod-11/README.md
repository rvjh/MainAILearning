# Evals Bootcamp (learner)

Lab code for RAG and multi-agent evaluation gates.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`. Set `LANGSMITH_API_KEY` if you use LangSmith.

## Layout

| Path | Contents |
|------|----------|
| `src/evaluated_agent/` | RAG agent + evaluators |
| `src/evaluated_agent/multi_agent/` | Supervisor multi-agent + eval |
| `src/evaluated_agent/production/` | Cost, budgets, safety, online sampling |
| `data/` | Corpus, goldens, baselines |
| `scripts/` | Runnable steps |
| `tests/` | Deterministic unit tests |
| `.github/workflows/` | CI gates |

## Run — checks (no API)

```bash
pytest -q
python scripts/13_production_checks.py
```

## Run — RAG

```bash
python scripts/00_preflight.py
python scripts/01_one_golden_case.py
python scripts/02_run_evaluation.py --split smoke
python scripts/03_compare_regression.py \
  --baseline data/baseline_report.json \
  --candidate reports/latest.json
python scripts/04_publish_langsmith.py
python scripts/02_run_evaluation.py --split full --gate
```

## Run — multi-agent

```bash
python scripts/10_multi_agent_one_case.py
python scripts/11_run_multi_agent_evaluation.py --split smoke
python scripts/12_compare_multi_agent_regression.py \
  --baseline data/multi_agent_baseline.json \
  --candidate reports/multi_agent_latest.json
python scripts/11_run_multi_agent_evaluation.py --split full --gate
```

## CI secrets

For GitHub Actions API jobs, add repository secrets:

- `OPENAI_API_KEY`
- `LANGSMITH_API_KEY`
