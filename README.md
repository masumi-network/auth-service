# Masumi Auth Service

Unified Sokosumi OAuth and token management for Masumi agents.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your values
```

## Run

```bash
uvicorn src.main:app --reload
```

## Test

```bash
pip install pytest pytest-asyncio
pytest -v
```
