# Session Notes: Replace MemorySaver with PostgreSQL

## What We Did

Replaced the in-memory `MemorySaver` checkpointer with a persistent PostgreSQL-backed setup. This was Tier 1, Step 1 from `DEPLOYMENT_PLAN.md`.

---

## Files Changed

| File | Change |
|------|--------|
| `app/graph.py` | Removed `MemorySaver` import and module-level `graph` singleton. `build_graph()` now accepts a `checkpointer` parameter — this is necessary because `PostgresSaver` requires a live DB connection pool, which only exists after startup (can't be created at import time). |
| `app/db.py` (new) | SQLAlchemy ORM model for `Ticket`, session management (`get_db` for routes, `get_session` for background tasks), and `init_db()` to create tables. |
| `app/main.py` | `lifespan` initializes both SQLAlchemy and the LangGraph checkpointer. Routes use `request.app.state.graph` and `Depends(get_db)`. Background tasks use `get_session()`. |
| `docker-compose.yml` | Added `postgres` service with healthcheck. API `depends_on` Postgres with `condition: service_healthy`. |
| `requirements.txt` | Added `langgraph-checkpoint-postgres`, `psycopg[binary,pool]`, `sqlalchemy`. |

---

## Key Decisions and Why

### Two separate connection pools to the same database
- `psycopg_pool.ConnectionPool` — used by `PostgresSaver` (LangGraph's checkpointer)
- SQLAlchemy's internal `QueuePool` — used by our ORM queries

They don't share connections. This is fine — total connection count is low and Postgres handles hundreds comfortably.

### ConnectionPool kwargs for PostgresSaver
```python
kwargs={
    "autocommit": True,      # Required: checkpointer.setup() runs CREATE INDEX CONCURRENTLY which can't be inside a transaction
    "row_factory": dict_row  # Required: PostgresSaver expects dict-style row access
}
```

### SQLAlchemy URL needs `+psycopg` suffix
`DATABASE_URL` uses the standard `postgresql://` scheme. SQLAlchemy defaults to `psycopg2` (the old driver) for that scheme. We installed `psycopg` (v3), so `init_db()` replaces the scheme with `postgresql+psycopg://` before passing it to `create_engine()`.

### DATABASE_URL only in docker-compose.yml, not .env
Since Postgres always runs inside Docker, the authoritative value (`postgresql://escalation:escalation@postgres:5432/escalation`) lives in the `api` service's `environment` block. No `.env` entry — avoids confusion about which hostname to use.

### Session management pattern
- **Route handlers**: `db: Session = Depends(get_db)` — FastAPI injects the session via dependency injection. The generator opens it, yields to the handler, and closes it in `finally`. This is the standard FastAPI pattern.
- **Background tasks**: `with get_session() as session:` — `Depends` doesn't work outside the request lifecycle, so we use the context manager protocol directly.
- **Why not import `SessionLocal` directly in main.py**: Python copies the reference at import time. Since `SessionLocal` starts as `None` and gets assigned inside `init_db()`, the imported copy stays `None`. The `get_db`/`get_session` functions always read the current module-level value.

### Own `tickets` table alongside LangGraph's internal tables
LangGraph's checkpointer stores full graph state but has no efficient "query all threads by field" API. We maintain a `tickets` table with the fields we need to query (`status`, `category`, `proposed_action`, etc.) to avoid iterating over checkpoint internals. Both live in the same Postgres database — LangGraph's tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) won't conflict with ours.

### Table creation approach
We use `Base.metadata.create_all(engine)` in `init_db()` — SQLAlchemy inspects the ORM models and runs `CREATE TABLE IF NOT EXISTS`. This is not as robust as migrations (Alembic) — you can't evolve the schema incrementally — but it's simple and appropriate for this project's current stage.

---

## Deferred / Not Done

- **Alembic migrations**: Considered but deferred — too much ceremony for this stage. If we need to add columns later, we'd either add Alembic then or alter the table manually.
- **`create_react_agent` deprecation warning**: The import from `langgraph.prebuilt` still works but prints a deprecation warning suggesting `from langchain.agents import create_agent`. The replacement has a different API signature, so fixing it requires rewriting agent invocation — separate task.
- **Remaining DEPLOYMENT_PLAN items**: Dockerfile CMD fix, docker-compose split (dev/prod), health check, error status, structured logging, env var validation.

---

## Useful Commands

```bash
# Connect to Postgres inside the running container
docker compose exec postgres psql -U escalation -d escalation

# Quick query from outside
docker compose exec postgres psql -U escalation -d escalation -c "SELECT ticket_id, status FROM tickets;"

# Inside psql
\dt                          -- list all tables
\d tickets                   -- show tickets table schema
SELECT * FROM tickets WHERE status = 'pending_approval';
SELECT status, COUNT(*) FROM tickets GROUP BY status;
```
