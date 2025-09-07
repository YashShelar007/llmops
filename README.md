# LLMOps Starter

A tiny, production-flavored LLM answering service to showcase LLMOps & Infrastructure skills:

- FastAPI backend with JSON logging
- Lightweight observability/tracing context (Langfuse hooks optional)
- Guardrail-ready request/response schema
- Cost/latency logging stubs
- Dockerfile and docker-compose for quick runs
- Placeholder eval harness & golden set for regression checks
- Minimal frontend planned (Next.js/React) — stubbed for now

## Quickstart (Local)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit:

- Health: http://localhost:8000/health
- Answer: POST http://localhost:8000/answer (JSON body: {"query":"Hello"})

## Quickstart (Docker)

```bash
docker compose up --build
```

## Repo Structure

```
backend/
  app/
    main.py
    models.py
    llm_client.py
    observability.py
  tests/
  requirements.txt
  Dockerfile
eval/
  golden_set.yaml
  harness.py
frontend/    # (will add minimal React/Next UI later)
infra/
  docker-compose.yml
```

## Notes

- Langfuse integration is optional and controlled by environment variables.
- LLM client is abstracted; by default it returns a deterministic mock for demo.
- Replace with your provider (e.g., OpenAI/Anthropic) by editing `llm_client.py`.
