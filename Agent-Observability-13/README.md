# Session-Observability

Theme: **The agent is running—but is it working?**

## Setup

```bash
cd Session-Observability
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional: add OPENAI_API_KEY / LANGSMITH_*
```

## Teaching commands (same as the slides)

```bash
python3 run_lab.py 00      # preflight FIRST
python3 run_lab.py primer  # telemetry intro (logs / metrics / traces)
python3 run_lab.py 01      # opening demo
python3 run_lab.py 02      # trace / bottleneck
python3 run_lab.py 03      # dashboard
python3 run_lab.py 04      # quality
python3 run_lab.py 05      # cost / budgets
python3 run_lab.py 06      # SLO + alerts
python3 run_lab.py 07      # hygiene
python3 run_lab.py all     # every lab (includes primer)
python3 run_lab.py tests   # pytest
```

Primer read-aloud: [`TELEMETRY-PRIMER.md`](TELEMETRY-PRIMER.md).  
Learner card: [`LEARNER-FOLLOW-ALONG.md`](LEARNER-FOLLOW-ALONG.md).

Teaching order: **preflight → primer → agent sketch → lab 01 → spans → LangSmith → health → ids → lab 02 → runtime/store → later labs**.

Open in the browser (from this folder):

- `interactive-slides.html` — audience + presenter deck
- `speaker-script.html` — word-for-word narration
- `LEARNER-FOLLOW-ALONG.md` — learner command order
- `DEMO-CHEATSHEET.md` — facilitator lab cue sheet

## Docker agent path (real queue + worker)

Uses `async-execution` (Postgres, Redis, Celery, FastAPI) with the Session-Observability support-ops agent.

```bash
cd Session-Observability
docker compose up --build
# other terminal:
source .venv/bin/activate
pip install httpx   # if needed
python scripts/docker_opening_demo.py
```

Submit any job with:

```json
"metadata": {
  "pipeline": "observability",
  "obs_scenario": "correct"
}
```

`obs_scenario` values match the local labs (`correct`, `confidently_wrong`, `slow_tool`, …).

Queue wait is real Celery/Redis delay — not the in-process sleep used by `run_lab.py`.

## Verify

```bash
pytest                 # offline / deterministic suite
pytest -m live -v      # real OpenAI using .env
python3 run_lab.py 00
```

## Layout

```
run_lab.py                 Slide-aligned local lab runner
docker-compose.yml         Dockerized API + worker path
docker/Dockerfile          Image: async-execution + obs_agent
interactive-slides.html    Deck (source of truth for order/timing/say)
speaker-script.html        Word-for-word narration (generated from slides)
LEARNER-FOLLOW-ALONG.md    Learner command order (generated)
DEMO-CHEATSHEET.md         Facilitator cue sheet (generated)
TELEMETRY-PRIMER.md        Primer card (generated from primer slide)
scripts/                   Labs 00–07 + docker_opening_demo.py + rebuild helper
src/obs_agent/             Agent + telemetry + quality/cost/SLO
tests/                     Automated checks
reports/                   Created by labs 03 and 06
```
