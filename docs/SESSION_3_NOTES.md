# Session 3 Notes — Production Hardening (2026-07-25)

## What We Implemented

### 1. Fixed Dockerfile CMD (Deployment Plan Point 2)
- Uncommented and updated the `CMD` line
- Removed `--reload` (dev-only, watches filesystem for changes)
- Added `--workers 4` for handling concurrent requests in production

### 2. Split Dev/Prod Docker Configs (Deployment Plan Point 3)
- Used **multi-stage builds** in a single `Dockerfile` with three targets:
  - `base` — shared layers (python, deps, app code)
  - `dev` — no CMD (VSCode handles running the server)
  - `prod` — uvicorn with 4 workers
- `docker-compose.yml` stays as the dev config (volume mounts, interactive mode, targets `dev`)
- `docker-compose.prod.yml` created for production (no volumes, targets `prod`, has restart policy)
- Run prod with: `docker compose -f docker-compose.prod.yml up --build`

### 3. Health Check Endpoint (Deployment Plan Point 4)
- Added `GET /health` returning `{"status": "ok"}` in `app/main.py`
- Placed above the `StaticFiles` mount (which catches all routes)
- Used by orchestrators (K8s, ECS) as a liveness probe

### 4. Environment Variable Validation (Deployment Plan Point 9)
- Validates `OPENAI_API_KEY` and `DATABASE_URL` at startup in the `lifespan` function
- Server fails fast with a clear error instead of starting and breaking on first request

### 5. Non-Root User in Production Image
- Created `appuser` with `--disabled-password --no-create-home` in the Dockerfile
- `prod` stage runs as `appuser` via `USER appuser`
- `dev` stage stays root (VSCode needs root for extensions/tools)
- `--no-create-home` skips creating `/home/appuser` — reduces image size and attack surface

### 6. API Service Health Check in docker-compose.prod.yml
- Uses Python's built-in `urllib` (no need to install curl in slim image)
- `start_period: 10s` — gives the app time to boot before checking
- `interval: 10s`, `retries: 3` — marks unhealthy after 3 failures
- Combined with `restart: unless-stopped` for automatic recovery

### 7. `.dockerignore`
- Prevents dev/IDE artifacts from being copied into the production image
- Excludes: `.git`, `.env`, `.vscode/`, `.devcontainer/`, `.claude/`, `__pycache__/`, compose files, Dockerfile itself
- Applies to all Docker builds, but only matters for prod (dev volume-mounts `.:/app` at runtime anyway)

---

## Key Learnings / Decisions

### `.dockerignore` syntax
- `.claude/` matches only a directory; `.claude` matches both files and directories

### Multi-stage builds avoid Dockerfile repetition
- Single `Dockerfile` with named stages (`base`, `dev`, `prod`)
- Compose files select the target: `build: { context: ., target: dev }`

### Why no CMD in dev stage
- VSCode Dev Container overrides the command anyway
- The container stays alive because docker-compose sets `stdin_open: true` and `tty: true`

---

## Open Security Concerns (Not Yet Fixed)

1. **No authentication** — all endpoints are open. API key auth was discussed but paused because:
   - The dashboard (served via StaticFiles) makes fetch() calls to the API
   - Embedding an API key in frontend JS is pointless (visible in dev tools)
   - Real options: session-based login, reverse proxy auth (Nginx/Cloudflare Access), or API key for programmatic access only with dashboard behind separate auth

2. **No rate limiting** — unlimited ticket submissions = unlimited LLM cost

3. **Postgres credentials hardcoded in compose** — should come from secrets manager in production

4. **No prompt injection protection** — ticket content goes directly to the LLM

---

## Files Changed
- `Dockerfile` — multi-stage build with non-root user
- `docker-compose.yml` — updated build target to `dev`
- `docker-compose.prod.yml` — new production compose (health check, restart policy)
- `.dockerignore` — new, excludes dev artifacts
- `app/main.py` — health endpoint, env var validation
