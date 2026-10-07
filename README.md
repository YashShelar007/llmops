# llmops

A small FastAPI service that answers a question with an LLM and returns latency, token count, cost and a trace ID with every answer. It is a reference deployment for people who want to see one LLM endpoint wired end to end on AWS: Lambda behind API Gateway, Terraform for the infra, GitHub Actions for deploys, Langfuse and CloudWatch for observability.

Request path: S3 static page, API Gateway (HTTP), Lambda container running FastAPI via Mangum, then OpenAI.

## What it does not do

- Only OpenAI is implemented, plus a canned mock provider for tests. The provider switch is one function, but no other vendor is wired in.
- Auth is a single shared API key checked against one header. There are no users, quotas or rate limits.
- Cost is a placeholder: the OpenAI path multiplies total tokens by a flat `0.000001`, not by real model pricing.
- The eval harness is a keyword check against three questions. It is a wiring example, not a quality gate.
- Metrics are written to a local JSONL file, which on Lambda lives in `/tmp` and is lost on cold start.

## Quickstart

Runs locally with the mock provider, no keys needed. Verified on Python 3.13 on macOS (2026-10-07).

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
LLM_PROVIDER=mock uvicorn app.main:app --port 8000
```

In another terminal:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/answer -H 'content-type: application/json' \
  -d '{"query":"What is the capital of France?"}'
python eval/harness.py     # run from the repo root; needs the server on :8000
```

With the mock provider all three golden-set questions pass. To use OpenAI, set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` (see `.env.example`). Not verified: the OpenAI path, Langfuse export, and `docker compose` in `infra/` (it expects a `.env` file at the repo root).

Endpoints: `GET /health`, `POST /answer` (body `{"query": "...", "user_id": "optional"}`), `GET /metrics` (last N rows of the metrics file), and the demo page at `/ui`.

## How it works

`POST /answer` checks the `X-API-Key` header if a `DEMO_API_KEY` is configured, then calls the LLM client inside a tracing span. The client retries with jittered exponential backoff (default 2 retries, 8 second timeout).

There is a small guardrail ladder. If the answer is empty or under three characters, the request is retried once with the query trimmed to 200 characters. If that also fails, or the provider raises, the caller gets a fixed "could you rephrase" message. The `guardrail` field in the response says which path was taken: `none`, `trimmed` or `fallback`.

Each request produces a structured JSON log line (structlog), one row in the metrics file, and, when `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` are all set, a Langfuse v3 trace over OpenTelemetry. The response carries both an app-level `request_id` and the Langfuse trace ID so the two can be joined.

Secrets can come from environment variables or from SSM Parameter Store: if `OPENAI_API_KEY` is unset and `SSM_OPENAI_API_KEY` names a parameter, it is fetched at import time. The same pattern covers the Langfuse keys and `DEMO_API_KEY`.

```
backend/app/       main.py (FastAPI), llm_client.py, observability.py, lambda_handler.py
eval/              golden_set.yaml, harness.py
frontend/          index.html (demo page)
infra/terraform/   Lambda, API Gateway, S3 website, CloudWatch alarms, SSM access
infra/docker-compose.yml
scripts/           dev_api.sh, plot_metrics.py, iam/gha-oidc-trust.json
.github/workflows/ ci, build-and-push, deploy-infra, deploy-ui, nightly-eval
```

## Deploying to AWS

Not verified: none of this was re-run in the 2026-10 cleanup. It needs the AWS CLI, Terraform, Docker Buildx and `jq`. Build for linux/amd64, push to ECR, deploy the image by digest.


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


## CI/CD

- `ci.yml`: starts the API with the mock provider and runs `eval/harness.py`; fails if any line says FAIL.
- `build-and-push.yml`: OIDC login, buildx for linux/amd64, push to ECR, capture the digest.
- `deploy-infra.yml`: resolve the image digest, then `terraform apply`.
- `deploy-ui.yml`: manual run that syncs `frontend/` to the S3 bucket named by the `UI_BUCKET` variable.
- `nightly-eval.yml`: one live call to `/answer` with the demo key, result kept as an artifact.

Repository variables used: `AWS_REGION`, `AWS_ACCOUNT_ID`, `ECR_REPO`, `AWS_ROLE_TO_ASSUME`, `API_BASE_URL`, `UI_BUCKET`. Secrets: `DEMO_API_KEY`, optionally `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`.

For the deploy role, edit `scripts/iam/gha-oidc-trust.json` so the account ID and the `repo:<owner>/<repo>:*` subject match your own, then create the role. Attach a policy scoped to ECR, Lambda, API Gateway, S3, IAM and CloudWatch for this stack; `AdministratorAccess` works but is far too broad to leave in place.

```bash
aws iam create-role --role-name gha-llmops-deployer \
  --assume-role-policy-document file://scripts/iam/gha-oidc-trust.json
```

## Configuration

- `LLM_PROVIDER`: `mock` (default) or `openai`.
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`), `OPENAI_MAX_TOKENS` (300), `OPENAI_TIMEOUT_S` (8).
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`: optional tracing.
- `DEMO_API_KEY`: if set, `/answer` requires it in `X-API-Key`.
- `METRICS_LOG`: metrics file path (`./metrics.jsonl`, or `/tmp/metrics.jsonl` on Lambda).
- `LLM_MOCK_FAIL_FIRST=true`: make the mock fail once, to exercise retries.

## Problems hit while building it

- Lambda rejected the image with "UnsupportedImageLayerDetected" or "InvalidImage": build for linux/amd64, disable provenance and SBOM, push with OCI media types off, and deploy by digest.
- S3 website policy returned AccessDenied: the account-level public access block has to allow public policies. The Terraform sets this.
- GitHub Actions failed with "No OpenIDConnect provider found": create the `token.actions.githubusercontent.com` provider in IAM first.
- Digest lookup returned null: use `aws ecr batch-get-image --image-ids imageTag=... --query 'images[0].imageId.imageDigest'`, or take the digest from the build step output.
- Langfuse rejected `.end(output=...)`: call `.update(output=...)` before closing the span, then `flush()`.

## Known limits

- CORS is `*` with credentials enabled in `backend/app/main.py`. Fine for a demo, wrong for anything with real users.
- `GET /metrics` is not behind the API key.
- No unit tests. The only automated check is the eval harness in CI.
- Not done: CloudFront and TLS for the UI, JWT auth, provisioned concurrency, a CloudWatch dashboard.

## Status

Built in 2025 as a starter project.

## License

MIT. See `LICENSE`.
