# Optional Redis/PostgreSQL path

The live class does not require containers. Use this path for the production mapping demo.

```bash
docker compose up -d
docker compose ps
```

Redis holds low-latency thread state and event cursors. PostgreSQL holds versioned long-term memory metadata, audit references, and the pgvector-derived index.

Do not switch to the container path during class if setup is not already green. The SQLite solution proves the same contracts and failure semantics.

