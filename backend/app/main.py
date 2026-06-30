"""
Waku Backend — FastAPI application for AI WhatsApp Assistant.
Indonesian MSMEs order management through WhatsApp.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.database import close_db, init_db
from app import models  # noqa: F401

load_dotenv()

# ── Logging ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("waku.backend")


# ── Lifespan ────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB. Shutdown: dispose engine."""
    await init_db()
    logger.info("Waku backend started.")
    yield
    await close_db()
    logger.info("Waku backend shut down.")


# ── App ─────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Waku Backend API",
    description="AI WhatsApp Assistant untuk UMKM Indonesia",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.constants import UPLOAD_DIR  # noqa: E402
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ── Health ───────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Simple health-check endpoint."""
    return {"status": "healthy", "service": "waku-backend"}


# ── Routers ──────────────────────────────────────────────────────────────────────
from app.api.routers import (  # noqa: E402
    webhook,
    auth,
    whatsapp,
    business,
    orders,
    customers,
    products,
    settings,
    staff,
    bookings,
    reports,
    media,
)

for _r in (webhook, auth, whatsapp, business, orders, customers, products, settings, staff, bookings, reports, media):
    app.include_router(_r.router)
