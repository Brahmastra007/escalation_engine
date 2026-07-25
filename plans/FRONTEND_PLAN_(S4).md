# Plan: Separate React Frontend for Escalation Engine

## Context

The Escalation Engine is an AI-powered ticket escalation system with a FastAPI backend. Currently it serves a static HTML dashboard (`static/index.html`) with inline JavaScript for approving/rejecting high-value refund tickets. There's no authentication — all endpoints are open.

The goal is to replace the static dashboard with a proper React frontend running as a separate service, and add JWT authentication to protect the API.

---

## Architecture

```
Browser → React (port 5173 dev / 3000 prod) → FastAPI API (port 8000) → PostgreSQL
```

- Frontend: Vite + React + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query
- Backend: FastAPI + JWT auth (new) + existing LangGraph endpoints
- Communication: REST over HTTP, JWT Bearer tokens
- Dev: Vite proxy forwards `/api/*` to backend (no CORS issues locally)
- Prod: Separate containers, CORS middleware on backend

---

## Phase 1: Backend Authentication

### 1.1 New dependencies in `requirements.txt`
- `PyJWT` — JWT encode/decode (actively maintained by jpadilla; `python-jose` is unmaintained since 2022)
- `bcrypt` — password hashing (maintained by PyCA; `passlib` is abandoned since 2020)

### 1.2 New file: `app/auth.py`
- `hash_password(plain)` / `verify_password(plain, hashed)` using `bcrypt` directly
- `create_access_token(data, expires_delta)` → signed JWT via `jwt.encode()`
- `get_current_user(token)` — FastAPI dependency that validates Bearer token from `Authorization` header, returns user dict
- Settings: `JWT_SECRET_KEY` (required, no default — must be set in `.env`) and `JWT_EXPIRY_HOURS` from env (default: 24h)

### 1.3 Add `User` model in `app/db.py`
```
users table: user_id (UUID PK), email (unique), password_hash, created_at
```

### 1.4 Seed admin user on startup
- In `lifespan()`, after `init_db()`, check if any user exists
- If none, create one from env vars `ADMIN_EMAIL` / `ADMIN_PASSWORD` (defaults: `admin@escalation.local` / `changeme`)
- No public registration endpoint — this is an internal tool

### 1.5 Auth endpoints in `app/main.py`
- `POST /api/auth/login` — validate credentials → returns `{access_token, token_type}`
- `GET /api/auth/me` — protected, returns current user info

### 1.6 Protect existing endpoints
- Add `Depends(get_current_user)` to: `POST /api/tickets`, `GET /api/tickets/{id}`, `GET /api/pending`, `POST /api/approve/{id}`
- Keep `GET /health` unprotected

### 1.7 Add CORS middleware
- Allow origin `http://localhost:5173` (dev) + configurable prod origins via `CORS_ORIGINS` env var
- Allow credentials, all methods, all headers

### 1.8 Remove static file serving
- Delete `app.mount("/", StaticFiles(...))` line from main.py
- Delete `static/index.html` (replaced by React app)
- Remove `StaticFiles` import

---

## Phase 2: React Frontend Setup

### 2.1 Initialize project
```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css              # Tailwind v4 CSS-based config (@import "tailwindcss")
│   ├── lib/utils.ts           # cn() helper (created by shadcn init)
│   ├── api/client.ts          # Axios instance + auth interceptor
│   ├── api/auth.ts            # login, me
│   ├── api/tickets.ts         # submit, getPending, approve, getTicket
│   ├── context/AuthContext.tsx # Auth state provider
│   ├── components/
│   │   ├── ui/               # shadcn/ui components (auto-generated)
│   │   ├── ProtectedRoute.tsx
│   │   └── Layout.tsx         # Nav header + content wrapper
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx      # Pending approvals table
│   │   ├── SubmitTicket.tsx
│   │   └── TicketDetail.tsx
│   └── types.ts               # API response types
├── index.html
├── vite.config.ts             # proxy /api → backend
├── components.json            # shadcn/ui config (created by shadcn init)
├── tsconfig.json
└── package.json
```

### 2.2 Key dependencies
- `react`, `react-dom`, `react-router-dom`
- `axios`
- `@tanstack/react-query`
- `tailwindcss` v4 (no postcss/autoprefixer needed — Tailwind v4 is a standalone CSS engine)
- shadcn/ui components: Button, Input, Label, Table, Card, Badge, Dialog, Sonner (toast)
  - `npx shadcn@latest init` (auto-detects Tailwind v4)
  - `npx shadcn@latest add button input label table card badge dialog sonner`

### 2.3 Vite config
- Dev proxy: `/api` → `http://localhost:8000` (running outside Docker) or `http://api:8000` (inside Docker)
- Frontend uses relative URLs (`/api/...`) — the proxy handles routing in dev, nginx reverse-proxy or CORS in prod
- Build output: `dist/`

---

## Phase 3: Frontend Implementation

### Pages

**Login** — email/password form (no registration, admin is seeded), stores JWT in localStorage, redirects to dashboard

**Dashboard** — table of pending tickets (mirrors current static HTML):
- Columns: Ticket ID, Customer Email, Category, Action/Amount, Draft Email, Approve/Reject buttons
- Auto-refreshes every 5s via TanStack Query `refetchInterval`
- Empty state when no pending tickets

**Submit Ticket** — form with customer_email + ticket_content fields, shows ticket_id on success

**Ticket Detail** (`/tickets/:id`) — full ticket state display, approve/reject if pending

### Auth flow
- `AuthContext` wraps app, checks localStorage for token on mount
- `ProtectedRoute` redirects to `/login` if not authenticated
- Axios interceptor attaches `Authorization: Bearer {token}` to all requests
- On 401 response: clear token, redirect to login

---

## Phase 4: Docker Integration

### 4.1 New file: `frontend/Dockerfile`
- Multi-stage: node:20-alpine builds the app, nginx:alpine serves it
- SPA fallback via nginx config (`try_files $uri /index.html`)
- Listens on port 3000

### 4.2 Update `docker-compose.dev.yml`
- Add frontend service running `npm run dev -- --host 0.0.0.0` on port 5173
- Mount source for hot reload

### 4.3 Update `docker-compose.prod.yml`
- Add frontend service with nginx, port 3000, depends on api

---

## Phase 5: Environment & Config

### Backend `.env` additions
```
JWT_SECRET_KEY=your-secret-here   # Required. Generate with: python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_EMAIL=admin@escalation.local
ADMIN_PASSWORD=changeme
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Frontend `.env`
```
VITE_API_BASE_URL=  # empty = use relative URLs via proxy (default for dev)
```
Note: In dev, Vite proxy routes `/api/*` to the backend. In prod, nginx handles the same. No absolute URL needed.

---

## Package Audit

Packages rejected during planning:

| Package | Problem | Replacement |
|---------|---------|-------------|
| `python-jose[cryptography]` | Unmaintained since 2022, known CVEs | `PyJWT` — actively maintained, same encode/decode API |
| `passlib[bcrypt]` | Abandoned since 2020, no Python 3.13 support | `bcrypt` directly — maintained by PyCA, simple `hashpw`/`checkpw` API |
| `tailwindcss` v3 | Requires `tailwind.config.ts` + `postcss.config.js` boilerplate | Tailwind v4 — CSS-native config, no JS config files |

All other packages (React ecosystem, FastAPI, SQLAlchemy, LangGraph) are actively maintained and current.

---

## Verification

1. Start backend: `docker-compose -f docker-compose.dev.yml up postgres api`
2. Start frontend: `cd frontend && npm install && npm run dev`
3. Test flow:
   - Open `http://localhost:5173` → redirected to login
   - Login with admin credentials → see empty dashboard
   - Submit a ticket (e.g. "refund my $100 order") → ticket enters processing
   - Wait ~10s for graph to complete → if refund >$50, appears in dashboard
   - Click Approve → ticket disappears from pending list
   - Check `/api/tickets/{id}` → status is "resolved"
4. Verify 401: clear localStorage token, try to access dashboard → redirected to login
