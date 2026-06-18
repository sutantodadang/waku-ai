# Waku 🤖 — AI WhatsApp Assistant for UMKM Indonesia

> *"Your AI shop assistant on WhatsApp — Rp30K/month"*

Waku helps Indonesian micro-business owners manage orders, answer customer questions, and grow sales — all through WhatsApp.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│  WhatsApp    │────▶│  Webhook API │────▶│   AI Core  │
│  Cloud API   │     │  (FastAPI)   │     │  (LLM/NLU) │
└─────────────┘     └──────┬───────┘     └────────────┘
                           │
                    ┌──────▼───────┐
                    │   Dashboard  │
                    │  (Streamlit) │
                    └──────────────┘
```

## Project Structure

```
waku-ai/
├── backend/          # FastAPI WhatsApp webhook + business logic
├── ai/               # LLM service (Bahasa Indonesia NLP)
├── dashboard/        # Streamlit web UI for business owners
└── docker-compose.yml
```

## Quick Start

Prerequisites: [uv](https://docs.astral.sh/uv/) (fast Python package manager).

```bash
# Backend
cd backend
uv sync
uv run uvicorn main:app --reload --port 8000

# AI Service (separate terminal)
cd ai
uv sync
uv run uvicorn ai_service:app --reload --port 8001

# Dashboard (separate terminal)
cd dashboard
uv sync
uv run streamlit run app.py

# Or all together with Docker
docker-compose up --build
```

## Configuration

Each service reads from a `.env` file in its directory. Copy the `.env.example` files:

```bash
# Backend — WhatsApp Cloud API credentials
cp backend/.env.example backend/.env
# Edit WHATSAPP_TOKEN, VERIFY_TOKEN in backend/.env

# AI Service — LLM provider settings
cp ai/.env.example ai/.env
# Edit OPENAI_API_KEY, OPENAI_BASE_URL (for GLM-5-2 etc.) in ai/.env

# Dashboard — backend URL
cp dashboard/.env.example dashboard/.env
```

## License

MIT
