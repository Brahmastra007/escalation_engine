# AWS Deployment Plan — Escalation Engine

Personal project deployment. Prioritizes learning and low cost over high availability.

---

## Architecture Overview

```
Route 53 (optional, custom domain)
         │
    CloudFront
    ├── /* (default)       → S3 (React static files)
    └── /api/*             → ALB → ECS Fargate (FastAPI)
                                        │
                                   RDS PostgreSQL
                                   (private subnet)

Secrets Manager ──► ECS Task Definition
ECR ──► ECS Task (Docker image)
```

---

## Cost Estimate (us-east-1, minimal traffic)

| Service | Monthly Cost |
|---------|-------------|
| ECS Fargate (0.25 vCPU, 0.5 GB, 1 task) | ~$9 |
| ALB | ~$16 |
| RDS db.t4g.micro (free tier eligible) | $0 (first 12 months) |
| S3 + CloudFront | < $1 |
| Secrets Manager (1 secret) | $0.40 |
| ECR | < $1 |
| **Total** | **~$27/month** (or ~$11 if RDS free tier) |

**Cost-saving tip:** When not using the app, scale ECS desired count to 0 and stop the RDS instance. This drops the cost to near-zero.

---

## Prerequisites

- AWS account with CLI configured (`aws configure`)
- Docker installed locally
- Node.js 20+ (for frontend build)
- A generated JWT secret: `openssl rand -hex 32`

---

## Step 1: VPC & Networking

Create a VPC with public and private subnets. ECS and ALB go in public subnets; RDS goes in private subnets.

```bash
# Use the AWS default VPC for simplicity (already has public subnets + IGW).
# Get your default VPC ID:
aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text

# Get default subnet IDs (you need at least 2 in different AZs for ALB):
aws ec2 describe-subnets --filters "Name=vpc-id,Values=<vpc-id>" --query "Subnets[*].[SubnetId,AvailabilityZone]" --output table
```

For RDS, create a private subnet group (or just use the default subnets with a restrictive security group — simpler for learning).

### Security Groups

Create 3 security groups in your VPC:

```bash
# 1. ALB security group — allows inbound HTTP/HTTPS from anywhere
aws ec2 create-security-group --group-name escalation-alb-sg --description "ALB" --vpc-id <vpc-id>
aws ec2 authorize-security-group-ingress --group-id <alb-sg-id> --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id <alb-sg-id> --protocol tcp --port 443 --cidr 0.0.0.0/0

# 2. ECS security group — allows inbound 8000 from ALB only
aws ec2 create-security-group --group-name escalation-ecs-sg --description "ECS tasks" --vpc-id <vpc-id>
aws ec2 authorize-security-group-ingress --group-id <ecs-sg-id> --protocol tcp --port 8000 --source-group <alb-sg-id>

# 3. RDS security group — allows inbound 5432 from ECS only
aws ec2 create-security-group --group-name escalation-rds-sg --description "RDS" --vpc-id <vpc-id>
aws ec2 authorize-security-group-ingress --group-id <rds-sg-id> --protocol tcp --port 5432 --source-group <ecs-sg-id>
```

---

## Step 2: RDS PostgreSQL

```bash
aws rds create-db-instance \
  --db-instance-identifier escalation-db \
  --db-instance-class db.t4g.micro \
  --engine postgres \
  --engine-version 16 \
  --master-username escalation_admin \
  --master-user-password '<strong-password>' \
  --allocated-storage 20 \
  --db-name escalation \
  --vpc-security-group-ids <rds-sg-id> \
  --no-multi-az \
  --no-publicly-accessible \
  --backup-retention-period 7 \
  --storage-type gp3
```

Wait for it to become available (~5-10 minutes):
```bash
aws rds wait db-instance-available --db-instance-identifier escalation-db
```

Get the endpoint:
```bash
aws rds describe-db-instances --db-instance-identifier escalation-db --query "DBInstances[0].Endpoint.Address" --output text
```

Your DATABASE_URL will be:
```
postgresql://escalation_admin:<password>@<rds-endpoint>:5432/escalation
```

---

## Step 3: Secrets Manager

Store all secrets in one secret:

```bash
aws secretsmanager create-secret \
  --name escalation-engine/prod \
  --secret-string '{
    "DATABASE_URL": "postgresql://escalation_admin:<password>@<rds-endpoint>:5432/escalation",
    "OPENAI_API_KEY": "<your-key>",
    "JWT_SECRET_KEY": "<output-of-openssl-rand-hex-32>",
    "LANGSMITH_API_KEY": "<your-key>",
    "ADMIN_EMAIL": "admin@escalation.local",
    "ADMIN_PASSWORD": "<strong-password>"
  }'
```

Note the ARN — you'll need it for the ECS task definition.

---

## Step 4: ECR — Build & Push the API Image

```bash
# Create repository
aws ecr create-repository --repository-name escalation-engine-api --region us-east-1

# Get the registry URI
REGISTRY=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com

# Login
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $REGISTRY

# Build and push
cd api
docker build --platform linux/amd64 --target prod -t escalation-engine-api .
docker tag escalation-engine-api:latest $REGISTRY/escalation-engine-api:latest
docker push $REGISTRY/escalation-engine-api:latest
```

> **Important:** Use `--platform linux/amd64` if you're building on an Apple Silicon Mac. Fargate runs x86_64 by default.

---

## Step 5: ECS Cluster + Task Definition + Service

### Create Cluster

```bash
aws ecs create-cluster --cluster-name escalation-engine
```

### Create IAM Roles

**Task Execution Role** (allows ECS to pull images and read secrets):

```bash
# Create the role
aws iam create-role --role-name ecsTaskExecutionRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach the managed policy
aws iam attach-role-policy --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Add Secrets Manager access
aws iam put-role-policy --role-name ecsTaskExecutionRole \
  --policy-name SecretsAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "<secret-arn>"
    }]
  }'
```

### Register Task Definition

Create `task-definition.json`:

```json
{
  "family": "escalation-engine-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/escalation-engine-api:latest",
      "portMappings": [
        { "containerPort": 8000, "protocol": "tcp" }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 10
      },
      "environment": [
        { "name": "LANGSMITH_TRACING", "value": "true" },
        { "name": "LANGSMITH_PROJECT", "value": "escalation-engine" },
        { "name": "LANGSMITH_ENDPOINT", "value": "https://aws.api.smith.langchain.com" },
        { "name": "CORS_ORIGINS", "value": "https://<cloudfront-domain>" }
      ],
      "secrets": [
        { "name": "DATABASE_URL", "valueFrom": "<secret-arn>:DATABASE_URL::" },
        { "name": "OPENAI_API_KEY", "valueFrom": "<secret-arn>:OPENAI_API_KEY::" },
        { "name": "JWT_SECRET_KEY", "valueFrom": "<secret-arn>:JWT_SECRET_KEY::" },
        { "name": "LANGSMITH_API_KEY", "valueFrom": "<secret-arn>:LANGSMITH_API_KEY::" },
        { "name": "ADMIN_EMAIL", "valueFrom": "<secret-arn>:ADMIN_EMAIL::" },
        { "name": "ADMIN_PASSWORD", "valueFrom": "<secret-arn>:ADMIN_PASSWORD::" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/escalation-engine-api",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "api",
          "awslogs-create-group": "true"
        }
      }
    }
  ]
}
```

```bash
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

### Create ALB + Target Group

```bash
# Create ALB
aws elbv2 create-load-balancer --name escalation-alb \
  --subnets <subnet-1> <subnet-2> \
  --security-groups <alb-sg-id> \
  --scheme internet-facing --type application

# Create target group
aws elbv2 create-target-group --name escalation-api-tg \
  --protocol HTTP --port 8000 \
  --vpc-id <vpc-id> \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30

# Create listener (HTTP for now — add HTTPS later with ACM cert)
aws elbv2 create-listener --load-balancer-arn <alb-arn> \
  --protocol HTTP --port 80 \
  --default-actions Type=forward,TargetGroupArn=<tg-arn>
```

### Create ECS Service

```bash
aws ecs create-service --cluster escalation-engine \
  --service-name escalation-api \
  --task-definition escalation-engine-api \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-1>,<subnet-2>],securityGroups=[<ecs-sg-id>],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=<tg-arn>,containerName=api,containerPort=8000"
```

> `assignPublicIp=ENABLED` lets ECS tasks reach the internet (OpenAI API, LangSmith) without a NAT Gateway — saves ~$32/month.

---

## Step 6: Frontend — S3 + CloudFront

### Build and Upload to S3

```bash
cd frontend
npm ci
npm run build

# Create bucket
aws s3 mb s3://escalation-engine-frontend-<unique-suffix>

# Upload
aws s3 sync dist/ s3://escalation-engine-frontend-<unique-suffix>/ --delete
```

### Create CloudFront Distribution

This is easiest to do in the AWS Console (CloudFront > Create Distribution), but here's what to configure:

**Origin 1 — S3 (frontend):**
- Origin domain: `escalation-engine-frontend-<suffix>.s3.us-east-1.amazonaws.com`
- Origin access: Origin Access Control (OAC) — create a new one
- Default root object: `index.html`

**Origin 2 — ALB (API):**
- Origin domain: `<alb-dns-name>` (from `aws elbv2 describe-load-balancers`)
- Protocol: HTTP only (ALB listener is on port 80)

**Behaviors:**
| Path Pattern | Origin | Cache Policy | Origin Request Policy | Allowed Methods |
|---|---|---|---|---|
| `/api/*` | ALB | CachingDisabled | AllViewer | ALL (GET, POST, PUT, DELETE, etc.) |
| `Default (*)` | S3 | CachingOptimized | — | GET, HEAD |

**Error Pages (for SPA routing):**
- 403 → `/index.html`, response code 200
- 404 → `/index.html`, response code 200

### S3 Bucket Policy (allow CloudFront OAC)

After creating the distribution, update the S3 bucket policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "cloudfront.amazonaws.com" },
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::escalation-engine-frontend-<suffix>/*",
    "Condition": {
      "StringEquals": {
        "AWS:SourceArn": "arn:aws:cloudfront::<account-id>:distribution/<distribution-id>"
      }
    }
  }]
}
```

```bash
aws s3api put-bucket-policy --bucket escalation-engine-frontend-<suffix> \
  --policy file://bucket-policy.json
```

---

## Step 7: Update CORS_ORIGINS

Once CloudFront is deployed, grab the distribution domain:
```bash
aws cloudfront list-distributions --query "DistributionList.Items[0].DomainName" --output text
```

Update the ECS task definition's `CORS_ORIGINS` environment variable to:
```
https://<abc123>.cloudfront.net
```

Then force a new deployment:
```bash
aws ecs update-service --cluster escalation-engine --service escalation-api --force-new-deployment
```

---

## Step 8: Verify

1. Visit `https://<cloudfront-domain>` — you should see the React login page
2. Login with your admin credentials
3. Submit a ticket and verify the LangGraph pipeline runs
4. Check logs: `aws logs tail /ecs/escalation-engine-api --follow`

---

## Optional: Custom Domain + HTTPS

1. Register/use a domain in Route 53
2. Request an ACM certificate (us-east-1 for CloudFront):
   ```bash
   aws acm request-certificate --domain-name escalation.yourdomain.com \
     --validation-method DNS --region us-east-1
   ```
3. Validate via DNS (Route 53 makes this one-click in Console)
4. Attach certificate to CloudFront distribution
5. Add Route 53 A record (Alias) → CloudFront distribution

---

## Day-to-Day Operations

**Deploy new API code:**
```bash
cd api
docker build --platform linux/amd64 --target prod -t escalation-engine-api .
docker tag escalation-engine-api:latest $REGISTRY/escalation-engine-api:latest
docker push $REGISTRY/escalation-engine-api:latest
aws ecs update-service --cluster escalation-engine --service escalation-api --force-new-deployment
```

**Deploy new frontend:**
```bash
cd frontend
npm run build
aws s3 sync dist/ s3://escalation-engine-frontend-<suffix>/ --delete
aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/*"
```

**Save money when not using:**
```bash
# Stop
aws ecs update-service --cluster escalation-engine --service escalation-api --desired-count 0
aws rds stop-db-instance --db-instance-identifier escalation-db

# Start
aws rds start-db-instance --db-instance-identifier escalation-db
aws rds wait db-instance-available --db-instance-identifier escalation-db
aws ecs update-service --cluster escalation-engine --service escalation-api --desired-count 1
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| ECS task keeps crashing | Check logs: `aws logs tail /ecs/escalation-engine-api --follow` |
| Task can't reach RDS | Verify ECS SG is allowed in RDS SG inbound rules |
| Task can't reach internet | Ensure `assignPublicIp=ENABLED` in service network config |
| CloudFront `/api/*` returns 503 | Check ALB target group health, ensure ECS task is running |
| Frontend shows blank page | Check S3 has files, CloudFront error pages configured for SPA |
| CORS errors in browser | Verify `CORS_ORIGINS` matches your CloudFront domain exactly |
