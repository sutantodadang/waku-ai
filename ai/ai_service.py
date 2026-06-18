"""FastAPI AI Service for Waku — Bahasa Indonesia NLP & LLM Assistant.

Endpoints:
- GET  /health          — Health check
- POST /ai/reply         — Generate AI reply
- POST /ai/extract-order — Extract structured order from chat
- POST /ai/summarize     — Generate daily business summary
- POST /ai/catalog-search— Search products in catalog
"""

import logging
import sys
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import settings
from conversation import (
    generate_reply,
    extract_order_from_chat,
    generate_daily_summary,
    manager as conversation_manager,
    search_catalog,
)

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("waku-ai")

# ── FastAPI app ──
app = FastAPI(
    title="Waku AI Service",
    description="Bahasa Indonesia NLP & LLM Assistant for UMKM",
    version="1.0.0",
)


# ──────────────────────────────────────────────
#  Request/Response models
# ──────────────────────────────────────────────

class ReplyRequest(BaseModel):
    business_context: Optional[dict] = Field(default=None, description="Business info (store_name, owner_name, etc.)")
    message_history: list[dict] = Field(default_factory=list, description="Previous messages [{'role','content'}]")
    incoming_message: str = Field(..., description="Customer's latest message")
    catalog: Optional[list[dict]] = Field(default=None, description="Product catalog [{name, price, stock}]")
    session_id: str = Field(default="default", description="Conversation/session identifier")


class ReplyResponse(BaseModel):
    reply: str = Field(..., description="AI-generated reply in Bahasa Indonesia")
    intent: str = Field(default="UNKNOWN", description="Detected intent")
    session_id: str = Field(default="default")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ExtractOrderRequest(BaseModel):
    messages: list[dict] = Field(..., description="Chat messages [{'role','content'}]")
    catalog: Optional[list[dict]] = Field(default=None, description="Product catalog")


class ExtractOrderResponse(BaseModel):
    items: list[dict] = Field(default_factory=list, description="Order items [{name, qty, price}]")
    total: float = Field(default=0.0, description="Order total")
    notes: str = Field(default="", description="Additional notes")


class SummarizeRequest(BaseModel):
    today_messages: list[dict] = Field(..., description="Today's messages with role, content, session_id, timestamp")
    business_context: Optional[dict] = Field(default=None)


class CatalogSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    catalog: list[dict] = Field(..., description="Product catalog to search in")


# ──────────────────────────────────────────────
#  Endpoints
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "waku-ai",
        "timestamp": datetime.now().isoformat(),
        "conversations_active": conversation_manager.count(),
        "llm_provider": "openai" if settings.use_openai else "ollama",
        "model": settings.llm_model if settings.use_openai else settings.ollama_model,
    }


@app.post("/ai/reply", response_model=ReplyResponse)
async def ai_reply(request: ReplyRequest):
    """Generate an AI reply for an incoming message."""
    try:
        # Pre-populate conversation with message history if provided
        if request.message_history:
            conv = conversation_manager.get_or_create(request.session_id)
            for msg in request.message_history[-settings.max_context_messages:]:
                if msg.get("role") in ("user", "assistant"):
                    conv.add_message(msg["role"], msg["content"])

        reply = generate_reply(
            session_id=request.session_id,
            incoming_message=request.incoming_message,
            business_context=request.business_context,
            catalog=request.catalog,
        )

        # Get the intent from the last analysis (stored in conv)
        from nlu import analyze_message
        catalog_names = []
        if request.catalog:
            catalog_names = [item.get("name", "") for item in request.catalog]
        analysis = analyze_message(request.incoming_message, catalog_items=catalog_names)

        return ReplyResponse(
            reply=reply,
            intent=analysis["intent"],
            session_id=request.session_id,
        )
    except Exception as e:
        logger.exception(f"Error in /ai/reply: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/extract-order", response_model=ExtractOrderResponse)
async def ai_extract_order(request: ExtractOrderRequest):
    """Extract structured order data from chat messages."""
    try:
        result = extract_order_from_chat(request.messages, request.catalog)
        return ExtractOrderResponse(
            items=result["items"],
            total=result["total"],
            notes=result["notes"],
        )
    except Exception as e:
        logger.exception(f"Error in /ai/extract-order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/summarize")
async def ai_summarize(request: SummarizeRequest):
    """Generate a daily business summary in Bahasa Indonesia."""
    try:
        summary = generate_daily_summary(request.today_messages, request.business_context)
        return {
            "summary": summary,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_messages": len(request.today_messages),
        }
    except Exception as e:
        logger.exception(f"Error in /ai/summarize: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/catalog-search")
async def ai_catalog_search(request: CatalogSearchRequest):
    """Search products in catalog matching the query."""
    try:
        results = search_catalog(request.query, request.catalog)
        return {
            "query": request.query,
            "results": results,
            "count": len(results),
        }
    except Exception as e:
        logger.exception(f"Error in /ai/catalog-search: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
#  Startup / Shutdown
# ──────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("Waku AI Service starting...")
    logger.info(f"LLM Provider: {'OpenAI-compatible' if settings.use_openai else 'Ollama (local)'}")
    if settings.use_openai:
        logger.info(f"  Model: {settings.llm_model}")
        logger.info(f"  Base URL: {settings.openai_base_url}")
    else:
        logger.info(f"  Ollama Model: {settings.ollama_model}")
        logger.info(f"  Ollama URL: {settings.ollama_base_url}")
    logger.info(f"Max context messages: {settings.max_context_messages}")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Waku AI Service shutting down...")


# ──────────────────────────────────────────────
#  Main entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "ai_service:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
        log_level="info",
    )
