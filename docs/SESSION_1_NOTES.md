# Session Notes: Escalation Engine — Initial Build

## What We Built

A **Human-in-the-Loop Tri-Agent Customer Escalation Engine** using LangGraph, FastAPI, and Docker. The system classifies incoming support tickets, drafts responses or refund actions, pauses for human approval when refunds exceed $50, and dispatches a final email after approval.

---

## Architecture

```
POST /api/tickets → triage_node → resolution_node → needs_approval?
                                                         │
                                          YES (refund > $50) → human_review_node → dispatcher_node → END
                                          NO                 → dispatcher_node → END
```

- **Agent 1 (Triage):** Classifies tickets into billing/technical/refund using structured output
- **Agent 2 (Resolution):** Uses tools (lookup_customer, calculate_refund, draft_support_response) via a ReAct agent loop, then extracts a structured ProposedAction
- **Human Review Node:** Calls `interrupt()` to freeze the graph, waits for human input
- **Agent 3 (Dispatcher):** Sends the final email (or cancels if rejected)

---

## Key Technical Decisions and Lessons

### LangGraph State Machine
- `TicketState` is a `TypedDict` — the single source of truth that flows through all nodes
- Each node receives the full state, returns only the fields it changed
- `MemorySaver` stores checkpoints keyed by `thread_id` (= ticket_id)
- The graph is compiled once at module level and shared across all requests

### The Interrupt Pattern
- `interrupt()` inside a node freezes execution and saves state to the checkpointer
- **Critical:** When resumed, LangGraph re-runs the entire node from the top, not from after `interrupt()`
- `interrupt()` returns the value passed via `Command(resume=...)` on the second run
- **Solution:** We split into a separate `human_review_node` so the expensive LLM calls in `resolution_node` don't re-run on resume
- Status is set to `"pending_approval"` AFTER `graph.invoke()` returns and `snapshot.next` confirms the graph is frozen

### Conditional Edges
- `add_conditional_edges("resolution", _needs_human_review)` routes to either `human_review` or `dispatcher`
- The routing function is a plain Python function that reads state and returns a node name string

### Structured Output
- `llm.with_structured_output(PydanticModel)` forces the LLM to return a specific schema
- `Literal["refund", "support_response"]` constrains the `type` field to exact values — prevents the LLM from returning variations like "Refund" or "refund_request" that would bypass the interrupt condition

### FastAPI + BackgroundTasks
- `graph.invoke()` is blocking (5-15s) — run it in BackgroundTasks so HTTP responses are instant
- `graph.get_state(config)` is the public API for reading checkpoint state — never access `checkpointer.storage` directly
- `_all_ticket_ids` set tracks submitted tickets since LangGraph has no "list all threads" API

### How the OpenAI Key Flows
```
.env → load_dotenv() at startup → os.environ → ChatOpenAI reads it automatically on first API call
```
Key is read lazily at call time, not at construction time — so module-level `ChatOpenAI()` objects work fine.

---

## Docker Learnings

### Layer Caching
- `COPY requirements.txt` + `RUN pip install` BEFORE `COPY . .` — code changes don't invalidate the dependency cache
- Chain commands in one `RUN` to avoid bloated layers (apt-get update + install + cleanup in one layer)

### Volume Mounts
- `volumes: .:/app` maps local source into the container for hot-reload during development
- Packages live in `/usr/local/lib/python3.12/site-packages/` (inside the image, NOT in /app) — volume mount doesn't affect them
- Changing `requirements.txt` requires `docker compose up --build`; changing `.py` files does not (uvicorn --reload handles it)

### SSL/Certificate Issues in Corporate Environments
- Corporate proxies intercept HTTPS with their own certificate
- The container's OS doesn't trust the corporate CA by default
- `update-ca-certificates` updates the OS store BUT `httpx`/Python HTTP libraries use `certifi`'s own bundle
- Fix: append the corporate cert into certifi's bundle: `cat cert.crt >> $(python -c "import certifi; print(certifi.where())")`
- Or set `SSL_CERT_FILE` and `HTTPX_CA_BUNDLE` env vars pointing to the cert file

---

## LangSmith Integration

### What It Provides
- Automatic tracing of every LLM call, tool invocation, and node execution
- Full prompt/response visibility, token counts, latency, and cost

### Setup
- `LANGSMITH_API_KEY` — authentication
- `LANGSMITH_TRACING=true` — master on/off switch
- `LANGSMITH_PROJECT=escalation-engine` — groups traces under a named project
- `LANGSMITH_ENDPOINT` — can point to AWS or GCP hosted endpoint
- **The project must already exist in LangSmith** — it does NOT auto-create and returns a cryptic 403 if missing

### Code Changes
- `@traceable(name="run-ticket-graph")` on `_run_graph` and `_resume_graph` makes them the root span so interrupt + resume appear as related traces
- `run_name` and `metadata` in the graph config label each trace with ticket ID and customer email for searchability
- All LangChain/LangGraph calls are auto-instrumented — no manual wrapping needed

---

## File Structure

```
escalation_engine/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI endpoints, background task runners
│   ├── graph.py             # LangGraph state machine definition
│   ├── state.py             # TicketState TypedDict
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── triage.py        # Agent 1 — classify tickets
│   │   ├── resolution.py    # Agent 2 — draft actions with tools
│   │   ├── human_review.py  # Interrupt node — pause for human
│   │   └── dispatcher.py    # Agent 3 — send final email
│   └── tools/
│       ├── __init__.py
│       └── mock_db.py       # Mock CRM/billing tools
├── static/
│   └── index.html           # Approval dashboard (plain HTML + fetch)
├── .env                     # Secrets (OPENAI_API_KEY, LANGSMITH_*)
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── DEPLOYMENT_PLAN.md       # Next steps for production readiness
└── SESSION_NOTES.md         # This file
```

---

## What's Next (see DEPLOYMENT_PLAN.md)

1. Replace MemorySaver with PostgreSQL checkpointer (most critical)
2. Fix Dockerfile CMD (currently commented out)
3. Split docker-compose into dev/prod configs
4. Add health check endpoint
5. Error status handling in state
6. Structured logging
7. Env var validation at startup
