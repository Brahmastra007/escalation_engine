# AWS Deployment Plan (Console/UI) — Escalation Engine

Same architecture as the CLI plan, but every step done through the AWS Management Console. Good for learning — you see what each service looks like and how they connect.

---

## Architecture

```
CloudFront (CDN)
├── /* (default)       → S3 (React static files)
└── /api/*             → ALB → ECS Fargate (FastAPI)
                                    │
                               RDS PostgreSQL
                               (private subnet)

Secrets Manager ──► ECS Task Definition
ECR ──► ECS Task (Docker image)
```

---

## Prerequisites

- AWS account (free tier eligible for RDS)
- Docker installed locally (to build the API image)
- AWS CLI configured (`aws configure`) — only needed for `docker push` to ECR
- Node.js 20+ (to build the frontend)

---

## Step 1: Security Groups

Go to **EC2 > Security Groups > Create security group**

Create 3 security groups (all in the default VPC):

### SG 1: `escalation-alb-sg`
| Type | Port | Source |
|------|------|--------|
| Inbound HTTP | 80 | 0.0.0.0/0 |
| Inbound HTTPS | 443 | 0.0.0.0/0 |

### SG 2: `escalation-ecs-sg`
| Type | Port | Source |
|------|------|--------|
| Inbound Custom TCP | 8000 | `escalation-alb-sg` (select from dropdown) |

### SG 3: `escalation-rds-sg`
| Type | Port | Source |
|------|------|--------|
| Inbound PostgreSQL | 5432 | `escalation-ecs-sg` (select from dropdown) |

---

## Step 2: RDS PostgreSQL

Go to **RDS > Create database**

| Setting | Value |
|---------|-------|
| Creation method | Standard create |
| Engine | PostgreSQL 16 |
| Templates | **Free tier** |
| DB instance identifier | `escalation-db` |
| Master username | `escalation_admin` |
| Master password | (set a strong password, note it down) |
| Instance class | db.t4g.micro |
| Storage | 20 GB gp3 |
| VPC | Default VPC |
| Public access | **No** |
| VPC security group | Remove default, add `escalation-rds-sg` |
| Initial database name | `escalation` |
| Backup retention | 7 days |
| Multi-AZ | No (not needed for personal project) |

Click **Create database**. Wait ~5 minutes for it to become available.

Once ready, go to the instance details and copy the **Endpoint** (e.g., `escalation-db.abc123.us-east-1.rds.amazonaws.com`).

Your DATABASE_URL is:
```
postgresql://escalation_admin:<password>@<endpoint>:5432/escalation
```

---

## Step 3: Secrets Manager

Go to **Secrets Manager > Store a new secret**

| Setting | Value |
|---------|-------|
| Secret type | Other type of secret |
| Key/value pairs | Add these: |

| Key | Value |
|-----|-------|
| `DATABASE_URL` | `postgresql://escalation_admin:<password>@<rds-endpoint>:5432/escalation` |
| `OPENAI_API_KEY` | Your OpenAI key |
| `JWT_SECRET_KEY` | Run `openssl rand -hex 32` locally, paste output |
| `LANGSMITH_API_KEY` | Your LangSmith key |
| `ADMIN_EMAIL` | `admin@escalation.local` |
| `ADMIN_PASSWORD` | A strong password |

Click **Next**.

| Setting | Value |
|---------|-------|
| Secret name | `escalation-engine/prod` |

Click through and **Store**. Copy the **Secret ARN** from the detail page.

---

## Step 4: ECR — Create Repository & Push Image

### In Console:

Go to **ECR > Repositories > Create repository**

| Setting | Value |
|---------|-------|
| Visibility | Private |
| Repository name | `escalation-engine-api` |

Click **Create repository**.

### On your local machine (terminal):

Click into the repository and click **View push commands** — AWS gives you exact copy-paste commands. They look like:

```bash
# 1. Login
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# 2. Build (from the api/ directory)
cd api
docker build --platform linux/amd64 --target prod -t escalation-engine-api .

# 3. Tag
docker tag escalation-engine-api:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/escalation-engine-api:latest

# 4. Push
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/escalation-engine-api:latest
```

> Use `--platform linux/amd64` if on Apple Silicon Mac.

---

## Step 5: ECS — Cluster

Go to **ECS > Clusters > Create cluster**

| Setting | Value |
|---------|-------|
| Cluster name | `escalation-engine` |
| Infrastructure | AWS Fargate (default) |

Click **Create**.

---

## Step 6: ECS — Task Definition

Go to **ECS > Task definitions > Create new task definition**

### Task definition configuration
| Setting | Value |
|---------|-------|
| Task definition family | `escalation-engine-api` |
| Launch type | AWS Fargate |
| OS/Architecture | Linux/X86_64 |
| CPU | 0.25 vCPU |
| Memory | 0.5 GB |
| Task execution role | Create new or select `ecsTaskExecutionRole` |

### Container 1
| Setting | Value |
|---------|-------|
| Name | `api` |
| Image URI | `<account-id>.dkr.ecr.us-east-1.amazonaws.com/escalation-engine-api:latest` |
| Container port | 8000, TCP |

**Health check:**
| Setting | Value |
|---------|-------|
| Command | `CMD-SHELL, python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"` |
| Interval | 30 |
| Timeout | 5 |
| Start period | 10 |
| Retries | 3 |

**Environment variables** (plain text — non-sensitive):
| Key | Value |
|-----|-------|
| `LANGSMITH_TRACING` | `true` |
| `LANGSMITH_PROJECT` | `escalation-engine` |
| `LANGSMITH_ENDPOINT` | `https://aws.api.smith.langchain.com` |
| `CORS_ORIGINS` | `http://localhost:5173` (update later with CloudFront domain) |

**Environment variables** (from Secrets Manager — use "ValueFrom"):
| Key | ValueFrom |
|-----|-----------|
| `DATABASE_URL` | `<secret-arn>:DATABASE_URL::` |
| `OPENAI_API_KEY` | `<secret-arn>:OPENAI_API_KEY::` |
| `JWT_SECRET_KEY` | `<secret-arn>:JWT_SECRET_KEY::` |
| `LANGSMITH_API_KEY` | `<secret-arn>:LANGSMITH_API_KEY::` |
| `ADMIN_EMAIL` | `<secret-arn>:ADMIN_EMAIL::` |
| `ADMIN_PASSWORD` | `<secret-arn>:ADMIN_PASSWORD::` |

**Logging:**
| Setting | Value |
|---------|-------|
| Log driver | `awslogs` |
| Log group | `/ecs/escalation-engine-api` (auto-create) |
| Stream prefix | `api` |

Click **Create**.

### Fix Task Execution Role Permissions

Go to **IAM > Roles > ecsTaskExecutionRole > Add permissions > Create inline policy**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "<secret-arn>"
    }
  ]
}
```

Name it `SecretsAccess` and save.

---

## Step 7: Application Load Balancer

Go to **EC2 > Load Balancers > Create Load Balancer > Application Load Balancer**

### Basic config
| Setting | Value |
|---------|-------|
| Name | `escalation-alb` |
| Scheme | Internet-facing |
| IP address type | IPv4 |
| VPC | Default VPC |
| Mappings | Select at least 2 AZs / subnets |
| Security group | `escalation-alb-sg` |

### Listeners and routing

Click **Create target group** (opens new tab):

| Setting | Value |
|---------|-------|
| Target type | IP addresses |
| Name | `escalation-api-tg` |
| Protocol/Port | HTTP / 8000 |
| VPC | Default VPC |
| Health check path | `/health` |
| Health check interval | 30 seconds |

Don't register targets manually (ECS does this automatically). Click **Create**.

Back on the ALB creation page:
| Setting | Value |
|---------|-------|
| Listener protocol/port | HTTP / 80 |
| Default action | Forward to `escalation-api-tg` |

Click **Create load balancer**.

Copy the **DNS name** from the ALB detail page (e.g., `escalation-alb-123456.us-east-1.elb.amazonaws.com`).

---

## Step 8: ECS — Service

Go to **ECS > Clusters > escalation-engine > Create service**

| Setting | Value |
|---------|-------|
| Launch type | Fargate |
| Task definition | `escalation-engine-api` (latest revision) |
| Service name | `escalation-api` |
| Desired tasks | 1 |

**Networking:**
| Setting | Value |
|---------|-------|
| VPC | Default VPC |
| Subnets | Same subnets as ALB |
| Security group | `escalation-ecs-sg` |
| Public IP | **Turned ON** (needed to reach OpenAI/LangSmith without NAT) |

**Load balancing:**
| Setting | Value |
|---------|-------|
| Type | Application Load Balancer |
| Load balancer | `escalation-alb` |
| Container to load balance | `api : 8000` |
| Target group | `escalation-api-tg` |

Click **Create service**.

### Verify

Wait 1-2 minutes, then visit:
```
http://<alb-dns-name>/health
```
You should see `{"status": "ok"}`.

---

## Step 9: S3 — Frontend Static Files

### Build locally:
```bash
cd frontend
npm ci
npm run build
```

### Create bucket:

Go to **S3 > Create bucket**

| Setting | Value |
|---------|-------|
| Bucket name | `escalation-engine-frontend-<unique-suffix>` |
| Region | us-east-1 |
| Block all public access | **ON** (CloudFront will access via OAC) |

Click **Create bucket**.

### Upload files:

Go into the bucket > **Upload** > drag the contents of `frontend/dist/` > **Upload**.

Or via CLI (faster for many files):
```bash
aws s3 sync dist/ s3://escalation-engine-frontend-<suffix>/ --delete
```

---

## Step 10: CloudFront Distribution

Go to **CloudFront > Create distribution**

### Origin 1 — S3 (frontend)
| Setting | Value |
|---------|-------|
| Origin domain | Select your S3 bucket from dropdown |
| Origin access | **Origin access control settings (recommended)** |
| Create new OAC | Name: `escalation-s3-oac`, Sign requests: Yes |

### Default behavior (already configured for Origin 1)
| Setting | Value |
|---------|-------|
| Viewer protocol policy | Redirect HTTP to HTTPS |
| Allowed HTTP methods | GET, HEAD |
| Cache policy | CachingOptimized |

### Settings
| Setting | Value |
|---------|-------|
| Default root object | `index.html` |
| Price class | Use only North America and Europe (cheapest) |

Click **Create distribution**.

### Add Origin 2 — ALB (API)

After creation, go to **Origins** tab > **Create origin**:

| Setting | Value |
|---------|-------|
| Origin domain | Paste ALB DNS name |
| Protocol | HTTP only |
| HTTP port | 80 |

### Add API Behavior

Go to **Behaviors** tab > **Create behavior**:

| Setting | Value |
|---------|-------|
| Path pattern | `/api/*` |
| Origin | Select the ALB origin |
| Viewer protocol policy | Redirect HTTP to HTTPS |
| Allowed HTTP methods | GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE |
| Cache policy | CachingDisabled |
| Origin request policy | AllViewer |

### Custom Error Pages (for SPA routing)

Go to **Error pages** tab > **Create custom error response**:

| HTTP error code | Response page path | HTTP response code |
|-----------------|--------------------|--------------------|
| 403 | `/index.html` | 200 |
| 404 | `/index.html` | 200 |

### Update S3 Bucket Policy

CloudFront will show a banner: "S3 bucket policy needs to be updated". Click **Copy policy**, then:

Go to **S3 > your bucket > Permissions > Bucket policy > Edit**, paste the policy, save.

---

## Step 11: Update CORS_ORIGINS

Copy your CloudFront domain from the distribution detail page (e.g., `d1a2b3c4d5e6f7.cloudfront.net`).

Go to **ECS > Task definitions > escalation-engine-api > Create new revision**

Update the `CORS_ORIGINS` environment variable:
```
https://d1a2b3c4d5e6f7.cloudfront.net
```

Click **Create**.

Then go to **ECS > Clusters > escalation-engine > escalation-api service > Update**:
- Select the new task definition revision
- Check **Force new deployment**
- Click **Update**

---

## Step 12: Verify Everything

1. Visit `https://<cloudfront-domain>` — React login page should load
2. Login with admin credentials
3. Submit a ticket, verify it processes
4. Check **CloudWatch > Log groups > /ecs/escalation-engine-api** for logs

---

## Optional: Custom Domain

### Request Certificate

Go to **ACM (Certificate Manager)** > **Request certificate** (must be in **us-east-1** for CloudFront):

| Setting | Value |
|---------|-------|
| Type | Public |
| Domain name | `escalation.yourdomain.com` |
| Validation method | DNS |

Click **Request**, then click into the certificate and click **Create records in Route 53** (if your domain is in Route 53).

### Attach to CloudFront

Go to **CloudFront > your distribution > General > Edit**:
- Alternate domain name (CNAME): `escalation.yourdomain.com`
- Custom SSL certificate: Select your ACM certificate

### DNS Record

Go to **Route 53 > Hosted zones > your domain > Create record**:
| Setting | Value |
|---------|-------|
| Record name | `escalation` |
| Record type | A |
| Alias | Yes |
| Route traffic to | CloudFront distribution |

---

## Day-to-Day Operations

### Deploy new API code

1. Build and push image locally (Step 4 terminal commands)
2. Go to **ECS > Clusters > escalation-engine > escalation-api > Update**
3. Check "Force new deployment" > **Update**

### Deploy new frontend

1. Run `npm run build` locally
2. Go to **S3 > bucket > Upload** (or use `aws s3 sync`)
3. Go to **CloudFront > distribution > Invalidations > Create invalidation**
   - Path: `/*`

### Save money when not using

**Stop:**
1. **ECS** > Cluster > Service > Update > Set desired tasks to **0**
2. **RDS** > Instance > Actions > **Stop temporarily**

**Start:**
1. **RDS** > Instance > Actions > **Start**
2. Wait for "Available" status
3. **ECS** > Cluster > Service > Update > Set desired tasks to **1**

---

## Troubleshooting

| Problem | Where to look |
|---------|---------------|
| ECS task won't start | ECS > Service > Events tab; also CloudWatch logs |
| "Secret not found" error | Check IAM role has SecretsAccess policy, ARN matches |
| ALB health check failing | EC2 > Target Groups > Targets tab (shows health status + reason) |
| CloudFront 503 on /api | Check ALB is healthy, origin domain is correct |
| Blank page on frontend | S3 bucket has files? CloudFront error pages set? Check browser console |
| CORS errors | `CORS_ORIGINS` must match CloudFront domain exactly (with `https://`) |
| Can't connect to RDS | ECS SG must be in RDS SG inbound rule |
