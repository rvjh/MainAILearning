# Learner follow-along


Work from: `Session-Observability/`


## Run in this order 

| Step | Command | What you should notice |
|---|---|---|
| 0 | `python3 run_lab.py 00` | Preflight OK before demos |
| 1 | `python3 run_lab.py primer` | log vs metric vs slow `cafe.grind` span |
| 2 | *(watch)* agent flow on slides | accept → queue → worker → validate |
| 3 | `python3 run_lab.py 01` | both `completed`; only one is a good customer outcome |
| 4 | *(Source)* `spans.py` | nested `with span()` ↔ parent/child |
| 5 | *(optional)* LangSmith UI | same questions; different ID than local `trace_id` |
| 6 | `python3 run_lab.py 02` | tool-heavy vs model-heavy latency |
| 7 | *(Source)* `runtime.py` → `store.py` | finish code walk after latency diagnosis |
| 8 | `python3 run_lab.py 03` | completed vs validated |
| 9 | `python3 run_lab.py 04` | citation without supporting evidence |
| 10 | `python3 run_lab.py 05` | success with a budget failure |
| 11 | `python3 run_lab.py 06` | alert → next action |
| 12 | `python3 run_lab.py 07` | redacted field vs raw export sibling |

Also useful: `python3 run_lab.py all` · `python3 run_lab.py tests`


