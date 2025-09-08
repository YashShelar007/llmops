# LLMOps Starter

Production-flavored LLM answering service that fits on a slide:

**S3 (UI)** → **API Gateway (HTTP)** → **Lambda (container) + FastAPI** → **OpenAI**
**Observability**: CloudWatch (structured JSON) + Langfuse v3 (OTel)
**Config/Secrets**: Env vars + SSM Parameter Store
**IaC/CI/CD**: Terraform + GitHub Actions (OIDC, no long-lived AWS keys)

---

## Features

* FastAPI backend (containerized) deployed to **AWS Lambda** behind **API Gateway**
* **OpenAI** provider (pluggable client), token & cost accounting per request
* **Langfuse v3** tracing (OpenTelemetry) + structured **CloudWatch** logs
* **API key** check (value stored in **SSM**) for a simple but real auth story
* Static **UI** hosted on **S3 website** with CORS to the API
* **Terraform** for Lambda, API GW, CORS, S3 website, alarms/logs
* **GitHub Actions**: build & push to ECR, deploy via Terraform, nightly eval
* Eval harness + golden set (kept simple but wiring is there)

---

## Repo Layout

```
backend/
  app/
    __init__.py          # SSM/env helpers, wiring
    main.py              # FastAPI + Mangum
    llm_client.py        # provider abstraction (OpenAI + mock)
    observability.py     # structlog + Langfuse v3 helpers
  requirements.txt
  Dockerfile.lambda
frontend/
  index.html             # Simple demo UI
infra/
  terraform/
    main.tf, variables.tf, outputs.tf, versions.tf
scripts/
  iam/gha-oidc-trust.json
.github/workflows/
  ci.yml                 # local mock tests, eval harness
  build-and-push.yml     # buildx -> ECR (amd64)
  deploy-infra.yml       # resolve digest -> terraform apply
  nightly-eval.yml       # scheduled live check
```

---

## Quickstart (Local Dev)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Minimal env (use your own key)
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
# Optional Langfuse
# export LANGFUSE_PUBLIC_KEY=pk_...
# export LANGFUSE_SECRET_KEY=sk_...
# export LANGFUSE_HOST=https://us.cloud.langfuse.com

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Endpoints:

* `GET /health`
* `POST /answer` with body `{"query":"Hello"}`

UI (served locally): open `frontend/index.html` and set API base to `http://localhost:8000`.

---

## Deploy to AWS (manual, fastest path)

**Prereqs:** AWS CLI, Terraform, Docker Buildx, `jq`.

1. **Build & push image** (amd64 is important for Lambda):

```bash
REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO=llmops-starter
aws ecr describe-repositories --repository-names "$REPO" \
  >/dev/null 2>&1 || aws ecr create-repository --repository-name "$REPO"

ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}"
aws ecr get-login-password --region "$REGION" \
 | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

docker buildx create --use --name llx >/dev/null 2>&1 || docker buildx use llx
docker buildx build -f backend/Dockerfile.lambda \
  --platform linux/amd64 \
  --tag "${ECR_URL}:lambda-amd64" \
  --provenance=false --sbom=false \
  --output=type=registry,oci-mediatypes=false,compression=gzip,force-compression=true \
  .
```

2. **Get digest and set image URI**:

```bash
DIGEST="$(aws ecr batch-get-image \
  --repository-name "${REPO}" \
  --image-ids imageTag="lambda-amd64" \
  --query 'images[0].imageId.imageDigest' \
  --output text --region "${REGION}")"

IMAGE_URI="${ECR_URL}@${DIGEST}"
echo "IMAGE_URI=${IMAGE_URI}"
```

3. **Terraform apply**:

```bash
cd infra/terraform
terraform init
terraform apply -auto-approve \
  -var "region=${REGION}" \
  -var "image_uri=${IMAGE_URI}" \
  -var "architecture=x86_64"
```

4. **Grab outputs**:

```bash
API_BASE=$(terraform output -raw api_base_url)
UI_URL=$(terraform output -raw ui_website_url)   # if you applied the UI module
echo "$API_BASE"
echo "$UI_URL"
```

5. **Create a demo API key in SSM** (if not created):

```bash
aws ssm put-parameter --name "/llmops-starter/demo_api_key" \
  --type "SecureString" --value "demo-please-change" --overwrite --region "$REGION"
```

6. **Call the API**:

```bash
DEMO=$(aws ssm get-parameter --with-decryption \
  --name "/llmops-starter/demo_api_key" --region "$REGION" \
  --query 'Parameter.Value' --output text)

curl -sS -X POST "${API_BASE}/answer" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${DEMO}" \
  -d '{"query":"Explain what an API is in one sentence."}' | jq
```

---

## CI/CD (GitHub Actions)

**What it does**

* `build-and-push.yml`: OIDC → ECR login → buildx (linux/amd64) → push → capture digest
* `deploy-infra.yml`: OIDC → resolve digest by tag (or use build output) → `terraform apply`
* `ci.yml`: local mock provider tests + eval harness (no spend)
* `nightly-eval.yml`: scheduled live call using the demo API key

**Repo → Settings → Variables (plain):**

* `AWS_REGION` = `us-east-1`
* `AWS_ACCOUNT_ID` = your account
* `ECR_REPO` = `llmops-starter`
* `AWS_ROLE_TO_ASSUME` = `arn:aws:iam::<account>:role/gha-llmops-deployer`

**Repo → Settings → Secrets (encrypted):**

* *(optional for CI logs)* `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
* *(for nightly-eval)* `DEMO_API_KEY` = value of `/llmops-starter/demo_api_key`

**OIDC role (one-time in AWS):**

* Edit `scripts/iam/gha-oidc-trust.json` → replace:

  * `<ACCOUNT_ID>` with your account
  * `<OWNER>/<REPO>` with your GitHub `owner/repo`
* Create role & attach policy (start with admin for speed; scope later):

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_NAME=gha-llmops-deployer
aws iam create-role --role-name "$ROLE_NAME" \
  --assume-role-policy-document file://scripts/iam/gha-oidc-trust.json
aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
echo "Role ARN: arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
```

> If Actions fails with *“No OpenIDConnect provider found…”*: create the OIDC provider
> `token.actions.githubusercontent.com` in IAM, then re-run.

---

## Demo Script (what to show the execs)

1. **UI (S3 website)** → paste `API_BASE` and the **demo API key** → ask a one-sentence “What is an API?”
   Call out: **latency, tokens, cost, guardrail, lf\_trace\_id** in the response JSON.
2. **Langfuse** → search by `lf_trace_id` → show input/output/tokens/cost, OTel resource attrs (service name/version/environment).
3. **CloudWatch logs** (or `aws logs tail`) → show the same `trace_id` & `lf_trace_id` in structured JSON.
4. **Security**: clear the API key and retry to show request rejection.
5. **Infra** (brief): show TF files for Lambda/API GW/S3 website/CORS/alarms; explain that deploys are **by digest**, so rollbacks are instant.

---

## Configuration & Secrets

* **Provider**: `LLM_PROVIDER=openai` (default), or `mock` for CI.
* **OpenAI**: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`)
* **Langfuse** (optional): `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
* **Demo API key**: stored in SSM `/llmops-starter/demo_api_key` and checked by the backend.
* **Metrics file**: defaults to `METRICS_LOG=/tmp/metrics.jsonl` on Lambda (ephemeral; clears on cold start).

---

## Troubleshooting (real issues we solved)

* **Lambda “UnsupportedImageLayerDetected” / “InvalidImage”**
  Build **linux/amd64**, disable provenance/SBOM, and push **OCI media types false**. Deploy **by digest**.
* **S3 website policy AccessDenied (BlockPublicPolicy)**
  Ensure the bucket’s Public Access Block allows public policy for website read; TF module sets this.
* **OIDC “No OpenIDConnect provider found”**
  Create the `token.actions.githubusercontent.com` OIDC provider and use the correct trust JSON (repo-scoped).
* **Digest lookup returns null**
  Prefer `aws ecr batch-get-image --image-ids imageTag=... --query 'images[0].imageId.imageDigest'`.
  Or capture `${{ steps.build.outputs.digest }}` directly in the build workflow.
* **Write to ./metrics.jsonl fails on Lambda**
  Use `/tmp/metrics.jsonl` or set `METRICS_LOG=/tmp/metrics.jsonl`.
* **Langfuse `.end(output=...)` error**
  Use `.update(output=...)` before closing the span; then `flush()`.

---

## Roadmap / nice-to-haves

* CloudFront + TLS + custom domain for the UI
* JWT auth (Cognito/Auth0) or API GW usage plans
* Provisioned Concurrency (1) to kill cold starts in demos
* CloudWatch dashboard + Slack alerts
* Larger eval set & quality gates

---

## License

MIT