# Deployment Readiness Plan

## Core Problem: MemorySaver

`MemorySaver` stores all ticket state in a Python dict in the process's RAM. In production this means:

- **Server restart = all in-flight tickets lost.** Every ticket in `pending_approval` or `processing` state vanishes.
- **Single process only.** You can never scale to more than one container instance — each instance has its own memory and they don't share state.
- **No persistence.** You can't query ticket history, audit past decisions, or recover from a crash.

Every other improvement below is secondary to fixing this.

---

## Tier 1 — Must Fix Before Any Real Deployment

### 1. Replace MemorySaver with PostgreSQL checkpointer

LangGraph ships a Postgres checkpointer (`langgraph-checkpoint-postgres`) that stores state in a real database. The graph code barely changes — you swap one import.

**What changes:**
- Add a Postgres service to `docker-compose.yml`
- Replace `MemorySaver()` with `PostgresSaver` in `app/graph.py`, passing a connection string
- Add `DATABASE_URL` to `.env`
- `_all_ticket_ids` in `app/main.py` can be replaced with a real DB query

### 2. Fix the CMD in Dockerfile

The `CMD` line is currently commented out. The container has no default command — it only works because the Dev Container overrides startup. In a real deployment the container would start and immediately exit.

```dockerfile
# Remove --reload (development only) and add workers for production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

`--reload` watches the filesystem for changes — it has no place in production. `--workers 4` runs multiple processes to handle concurrent requests.

### 3. Separate dev and prod Docker configs

The current `docker-compose.yml` has a volume mount (`. : /app`) which overlays local source code into the container. In production the code should be baked into the image, not mounted from a laptop.

- `docker-compose.yml` — production config, no volume mounts, no `--reload`
- `docker-compose.dev.yml` — development overrides, adds volume mount and `--reload`

---

## Tier 2 — Important for Reliability

### 4. Error status in state

If an LLM call fails, the ticket stays stuck at `"processing"` forever with no visibility. 

**What changes:**
- Add `"error"` status and `error_message: Optional[str]` field to `TicketState` in `app/state.py`
- In `_run_graph` in `app/main.py`, catch exceptions and write `{"status": "error", "error_message": str(e)}` into state via `graph.update_state()`

### 5. Remove redundant `graph.update_state` in `approve_ticket`

In `app/main.py`, `approve_ticket` calls `graph.update_state(config, {"approved": ..., "status": "processing"})` and also passes `approved` via `Command(resume={"approved": approved})`. The `update_state` call is unnecessary — `human_review_node` reads `approved` from `resume_data` returned by `interrupt()`, not from state. Remove the `update_state` call to avoid confusion.

### 6. `_all_ticket_ids` is not thread-safe

A Python `set` being written from background threads and read from async routes can cause race conditions. This goes away entirely once Postgres is in place — replace the set with a DB query.

---

## Tier 3 — Good Practice

### 7. Health check endpoint

Any orchestration system (Kubernetes, ECS, Railway) needs a `GET /health` endpoint returning 200 to know the container is alive. Without it, the platform can't detect crashes or route traffic.

```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

### 8. Structured logging instead of `print()`

Every `print()` in the agents should become a proper `logging` call with a JSON formatter. Production log aggregators (Datadog, CloudWatch, Loki) parse JSON logs — plain `print()` output is unstructured and hard to query.

### 9. Environment variable validation at startup

If `OPENAI_API_KEY` is missing the server starts fine but every request fails at the LLM call. Validate required env vars in `lifespan` in `app/main.py` and raise a clear error at startup if any are missing.

```python
REQUIRED_ENV_VARS = ["OPENAI_API_KEY"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {missing}")
    yield
```

---

## Recommended Build Order

| Step | Task | File(s) |
|------|------|---------|
| 1 | Postgres checkpointer | `app/graph.py`, `docker-compose.yml`, `.env`, `requirements.txt` |
| 2 | Fix Dockerfile CMD | `Dockerfile` |
| 3 | Split docker-compose files | `docker-compose.yml`, `docker-compose.dev.yml` |
| 4 | Health check endpoint | `app/main.py` |
| 5 | Error status in state | `app/state.py`, `app/main.py` |
| 6 | Remove redundant update_state | `app/main.py` |
| 7 | Structured logging | all `app/agents/*.py` files |
| 8 | Env var validation at startup | `app/main.py` |
