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
├── dashboard/        # Simple web UI for business owners
└── infra/            # Docker, deployment configs
```

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# AI Service
cd ai
pip install -r requirements.txt
python assistant.py

# Dashboard
cd dashboard
streamlit run app.py
```

## License

MIT
