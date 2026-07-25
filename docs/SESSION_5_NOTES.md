# Deployment Session Notes

Summary of deploying the Escalation Engine to AWS (July 2026).

---

## What We Deployed

| Layer | AWS Service | Config |
|-------|-------------|--------|
| Frontend | S3 + CloudFront | Static React build served via CDN |
| Backend | ECS Fargate + ALB | 1 task, 1 worker, 0.25 vCPU, 0.5 GB RAM |
| Database | RDS PostgreSQL 16 | db.t4g.micro, free tier, private subnet |
| Secrets | Secrets Manager | One JSON secret with all keys |
| Container Registry | ECR | Private repo for API Docker image |

---

## Architecture

```
CloudFront (single entry point)
├── /* (default)     → S3 (React static files via OAC)
└── /api/*           → ALB → ECS Fargate (FastAPI container)
                                    │
                               RDS PostgreSQL
                               (password auth, private)

Secrets Manager → injected as env vars into ECS task at startup
ECR → stores the API Docker image, pulled by ECS
```

---

## Key Decisions & Why

### Frontend: S3 + CloudFront (no nginx)
- Deleted `nginx.conf` and the `prod` stage from the frontend Dockerfile
- S3 stores files, CloudFront handles caching and SPA routing (via custom error pages 403/404 → index.html)
- No container running for the frontend at all

### Single CloudFront domain eliminates CORS
- Frontend and API share the same CloudFront domain (different paths)
- Browser sees same origin → no CORS preflight needed
- `CORS_ORIGINS` env var only matters for local development (`http://localhost:5173`)

### Security group chain
```
Internet → ALB (port 80/443) → ECS (port 8000) → RDS (port 5432)
```
- Each SG only allows inbound from the previous layer
- RDS is never reachable from the internet
- ALB must be internet-facing because CloudFront is outside the VPC

### 1 Uvicorn worker (not 4)
- 0.5 GB memory isn't enough for 4 workers each loading LangGraph + LangChain + SQLAlchemy
- Workers were dying and respawning in a loop
- 1 worker is sufficient for low-traffic personal use

### Password auth for RDS (not IAM)
- App connects via `DATABASE_URL` with username/password
- Simpler; IAM auth is for enterprise setups

### Public IP on ECS task
- Container needs outbound internet to reach OpenAI and LangSmith APIs
- `assignPublicIp=ENABLED` avoids needing a NAT Gateway (~$32/month savings)

### ALB required even though CloudFront calls it
- CloudFront runs outside your VPC on AWS's global edge network
- It reaches ALB over the public internet
- ECS Fargate tasks get dynamic IPs — ALB provides a stable endpoint
- AWS VPC Origins (private ALB option) exists but is more complex

---

## Code Changes Made

1. **`api/.dockerignore`** — added `.env` so secrets don't get baked into Docker images
2. **`api/Dockerfile`** — changed `--workers 4` to `--workers 1` (memory constraint)
3. **`frontend/nginx.conf`** — deleted (not needed with S3 + CloudFront)
4. **`frontend/Dockerfile`** — removed `prod` stage (nginx), kept `dev` and `build` stages

---

## Concepts Learned

### AWS CLI Profiles
- `aws configure --profile personal` keeps personal and company credentials isolated
- `export AWS_PROFILE=personal` avoids typing `--profile` every time
- Credentials stored in `~/.aws/credentials`, config in `~/.aws/config`

### Access Keys
- `AKIA...` prefix = long-term key (no session token needed)
- `ASIA...` prefix = temporary credentials (requires session token)
- The secret key signs requests using HMAC-SHA256 (AWS Signature V4)
- AWS stores a hash, not the plaintext — can't be retrieved after creation

### Security Groups vs NACLs
- Security groups: per-resource, stateful, allow-only rules
- NACLs: per-subnet, stateless, allow+deny rules, evaluated in order
- Default NACLs allow everything — usually don't need to touch them

### Outbound rules
- All SGs allow all outbound by default
- Only restrict in enterprise/compliance scenarios

### Task Execution Role vs Task Role
- Execution role: for ECS itself (pull images, read secrets)
- Task role: for your application code (call AWS APIs like S3, DynamoDB)
- This app doesn't call AWS APIs → no task role needed

### RDS access isn't an AWS API call
- It's a TCP connection (port 5432) authenticated with username/password
- Security group permits the network path; IAM isn't involved

### Building without Node.js locally
```bash
docker run --rm -v $(pwd):/app -w /app node:20-alpine npm install
docker build --target build -t escalation-frontend-build .
docker cp $(docker create escalation-frontend-build):/app/dist ./dist
```

### `npm ci` vs `npm install`
- `npm ci` requires `package-lock.json` — faster, deterministic
- `npm install` generates the lock file if it doesn't exist
- Lock file should be committed to git

---

## Cost Breakdown

| Service | Running | Idle (ECS=0, RDS stopped) |
|---------|---------|---------------------------|
| ECS Fargate | ~$9/month | $0 |
| ALB | ~$16/month | ~$16/month (always charges) |
| RDS (free tier) | $0 | $0 |
| S3 + CloudFront | < $1 | ~$0 |
| Secrets Manager | $0.40 | $0.40 |
| **Total** | **~$27/month** | **~$16.40/month** |

To get idle cost to ~$0.40, delete the ALB when not using.

---

## Day-to-Day Operations

### Redeploy API
```bash
cd api
docker build --platform linux/amd64 --target prod -t escalation-engine-api .
docker tag escalation-engine-api:latest <registry>/escalation-engine-api:latest
docker push <registry>/escalation-engine-api:latest
# Then: ECS → Service → Update → Force new deployment
```

### Redeploy Frontend
```bash
cd frontend
docker build --target build -t escalation-frontend-build .
docker cp $(docker create escalation-frontend-build):/app/dist ./dist
aws s3 sync dist/ s3://<bucket>/ --delete --profile personal
# Then: CloudFront → Invalidations → Create → /*
```

### Stop (save money)
1. ECS → Service → Update → desired tasks = 0
2. RDS → Instance → Actions → Stop temporarily

### Start
1. RDS → Instance → Actions → Start (wait for "Available")
2. ECS → Service → Update → desired tasks = 1

---

## Files Created

- `plans/AWS_DEPLOYMENT.md` — CLI-based deployment steps
- `plans/AWS_DEPLOYMENT_CONSOLE.md` — Console/UI-based deployment steps
- `docs/DEPLOYMENT_SESSION_NOTES.md` — this file
