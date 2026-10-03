# DashLens server

FastAPI backend for DashLens. It keeps the Agora App Certificate and all API keys off the phone, mints RTC/RTM tokens, starts and stops the Agora Conversational AI agent, serves the agent's tools (`/v1/tools/manual`, `/v1/tools/helpline`), and saves each call's transcript, camera frames and latency metrics to `transcripts/`.

Setup and architecture are in the [main README](../README.md). In short:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env.local                          # fill in the keys, set PUBLIC_BASE_URL
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Add a car's manual to the cache ahead of time:

```bash
python app/manual/manual_pipeline.py Hyundai Creta
```

Run the tests with `python -m pytest -q`.
