# Session Notes: React Frontend + JWT Auth

## What We Built

Transformed the Escalation Engine from a single FastAPI app serving static HTML into a proper two-service architecture: a React frontend and a FastAPI backend, both running in separate Docker containers with VS Code Dev Container support.

---

## Architecture

```
escalation_engine/
├── api/                         ← Python backend (FastAPI)
│   ├── app/                     ← Python package
│   │   ├── auth.py              ← NEW: JWT + bcrypt auth module
│   │   ├── db.py                ← MODIFIED: added User model
│   │   ├── main.py             ← MODIFIED: auth endpoints, CORS, protected routes
│   │   ├── graph.py, state.py, agents/, tools/  ← unchanged
│   ├── .devcontainer/           ← VS Code attaches to api container
│   ├── .vscode/launch.json      ← Python debugger config
│   ├── Dockerfile               ← dev + prod stages
│   ├── .env                     ← backend secrets (gitignored)
│   └── requirements.txt         ← added PyJWT, bcrypt
├── frontend/                    ← React app (Vite + TypeScript + Tailwind v4)
│   ├── src/
│   │   ├── api/client.ts        ← Axios with JWT interceptor
│   │   ├── api/auth.ts          ← login, getMe
│   │   ├── api/tickets.ts       ← submitTicket, getPending, approveTicket, getTicket
│   │   ├── context/AuthContext.tsx ← Auth state management
│   │   ├── components/Layout.tsx   ← Nav header with logout
│   │   ├── components/ProtectedRoute.tsx
│   │   ├── pages/Login.tsx
│   │   ├── pages/Dashboard.tsx  ← Pending approvals table (auto-refresh 5s)
│   │   ├── pages/SubmitTicket.tsx
│   │   ├── pages/TicketDetail.tsx
│   │   ├── types.ts             ← TypeScript interfaces for API responses
│   │   ├── App.tsx              ← Router + providers
│   │   └── index.css            ← @import "tailwindcss" (v4, CSS-only config)
│   ├── .devcontainer/           ← VS Code attaches to frontend container
│   ├── Dockerfile               ← dev / build / prod stages
│   ├── nginx.conf               ← prod SPA serving with caching
│   └── vite.config.ts           ← proxy /api → http://api:8000
├── docker-compose.dev.yml       ← postgres + api + frontend
├── docker-compose.prod.yml
└── corporate-ca.pem             ← shared cert (mounted into api)
```

---

## Key Decisions and Why

### Package choices

| Chose | Over | Why |
|-------|------|-----|
| PyJWT | python-jose | python-jose unmaintained since 2022, has known CVEs |
| bcrypt (direct) | passlib | passlib abandoned since 2020, no Python 3.13 support |
| Tailwind v4 | Tailwind v3 | No tailwind.config.ts/postcss.config.js needed — config lives in CSS |
| @tailwindcss/vite | postcss plugin | Official Vite plugin for v4, faster than PostCSS pipeline |
| TanStack Query | manual fetch + useState | Auto-refresh, caching, mutation state management for free |
| axios | fetch | Interceptors make it easy to attach JWT to every request |

### Auth approach

- **Seeded admin only** — no public registration. Admin email/password come from env vars (`ADMIN_EMAIL`, `ADMIN_PASSWORD`). Created on first startup if users table is empty.
- **JWT in localStorage** — simple for an internal tool. Token attached via axios request interceptor. On 401 response, token is cleared and user redirected to login.
- **`HTTPBearer` scheme** — FastAPI extracts token from `Authorization: Bearer <token>` header.

### Dev Container setup (Option 2: separate containers)

- Each service has its own `.devcontainer/devcontainer.json`
- Open `api/` folder → VS Code attaches to api container
- Open `frontend/` folder → VS Code attaches to frontend container
- Both reference the same `docker-compose.dev.yml` (all services start together)
- Frontend has `"overrideCommand": false` so the Vite dev server runs automatically
- Backend does NOT have this — you start uvicorn manually via F5 debugger

### Why .env lives in api/

- Only the backend needs secrets (OPENAI_API_KEY, JWT_SECRET_KEY, etc.)
- Allows frontend to have its own .env later for VITE_* variables
- docker-compose references it as `env_file: ./api/.env`
- `.env` in .gitignore matches at any depth (covers both api/.env and future frontend/.env)

### Docker volumes for node_modules

- Named volume `frontend_node_modules:/app/node_modules` prevents the bind mount (`./frontend:/app`) from overwriting installed packages
- **Gotcha:** named volumes persist stale packages across rebuilds. To refresh: `docker volume rm escalation_engine_frontend_node_modules` then rebuild

---

## Concepts Learned

### CORS (Cross-Origin Resource Sharing)
Browser blocks requests from one origin (localhost:5173) to another (localhost:8000). CORS middleware on the backend opts in to allow this. Config:
- `allow_origins` — which domains can call the API
- `allow_credentials` — allows Authorization header
- `allow_methods/headers` — which HTTP methods and headers are accepted

### Vite Proxy
In development, Vite forwards `/api/*` requests to the backend. This avoids CORS entirely in dev (browser thinks it's same-origin). In production, nginx or CORS handles it instead.

### JWT Flow
1. User submits email/password → backend verifies → returns signed JWT
2. Frontend stores JWT in localStorage
3. Every subsequent request includes `Authorization: Bearer <token>`
4. Backend decodes token, extracts user_id, looks up user in DB
5. If token expired/invalid → 401 → frontend clears token → redirects to login

### TanStack Query
- `useQuery` — fetches data, caches it, handles loading/error states, can auto-refetch on interval
- `useMutation` — handles write operations (POST), provides isPending/isSuccess/isError states
- `invalidateQueries` — after a mutation succeeds, marks cached data as stale so it refetches

### Tailwind v4 vs v3
- v3: requires tailwind.config.ts + postcss.config.js + autoprefixer
- v4: just `@import "tailwindcss"` in CSS + the Vite plugin. All config is CSS-based.
- IntelliSense needs `tailwindcss` package installed in node_modules to work

### Multi-stage Dockerfiles
- `dev` stage — has source code + dependencies, runs dev server with hot reload
- `build` stage — compiles/bundles for production
- `prod` stage — minimal image (nginx) with only the built output

### npm version specifiers
- `^19.2.7` — allows minor+patch updates (19.x.x but not 20.0.0)
- `~19.2.7` — allows patch only (19.2.x)
- No prefix — exact version

### nginx SPA serving
- `try_files $uri $uri/ /index.html` — if the URL doesn't match a real file, serve index.html (React Router handles the route client-side)
- Static assets (JS/CSS in /assets/) get 1-year cache headers because Vite adds content hashes to filenames — changed code = new filename = fresh download

---

## Backend .env Variables

```
OPENAI_API_KEY=...
DATABASE_URL=...                    (set by docker-compose, not in .env)
JWT_SECRET_KEY=...                  (generate with: python -c "import secrets; print(secrets.token_hex(32))")
JWT_EXPIRY_HOURS=24                 (optional, defaults to 24)
ADMIN_EMAIL=admin@escalation.local  (optional, default shown)
ADMIN_PASSWORD=changeme             (optional, default shown)
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=escalation-engine
LANGSMITH_ENDPOINT=https://aws.api.smith.langchain.com
```

---

## How to Run

**Backend development:**
1. Open `api/` in VS Code → "Reopen in Container"
2. All services start (postgres, api, frontend)
3. F5 to launch uvicorn with debugger
4. API at http://localhost:8000

**Frontend development:**
1. Open `frontend/` in VS Code → "Reopen in Container"
2. Vite dev server starts automatically
3. Frontend at http://localhost:5173

**Testing the full flow:**
1. http://localhost:5173 → redirected to /login
2. Login: admin@escalation.local / changeme
3. Submit a ticket with "refund my $100 order"
4. Wait ~10s → if refund >$50, appears in Dashboard
5. Approve/Reject from dashboard or ticket detail page
