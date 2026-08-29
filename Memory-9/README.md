# Learner starter

This starter intentionally contains five unsafe/TODO boundaries. It runs without API keys or network access.

```bash
python -m unittest discover -s tests -v
python demo.py
```

Start by running the suite and reading each failure:

```bash
python -m unittest discover -s tests -v
```

Expected baseline: **3 tests pass and 11 fail**. Those failures are intentional.

Then complete:

1. rolling-summary compaction;
2. governed write validation and policy;
3. deduplication, conflict handling, and supersession;
4. scope-first, TTL-aware, budgeted recall;
5. deletion propagation and tombstone evidence.

The final gate is **14 passing tests**.
