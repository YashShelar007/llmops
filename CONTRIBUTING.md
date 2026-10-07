# Contributing

Run the service with the mock provider and check the golden set:

    cd backend && pip install -r requirements.txt
    LLM_PROVIDER=mock uvicorn app.main:app --port 8000
    python eval/harness.py        # from the repo root, in a second terminal

CI runs the same harness and fails on any FAIL line. Open a PR against `main` with a short description of what changed and how you checked it. Add a question to `eval/golden_set.yaml` when you change answer behavior.
