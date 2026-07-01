"""FastAPI AI Service for Waku — Bahasa Indonesia NLP & LLM Assistant.

Endpoints:
- GET  /health          — Health check
- POST /ai/reply         — Generate AI reply
- POST /ai/extract-order — Extract structured order from chat
- POST /ai/summarize     — Generate daily business summary
- POST /ai/catalog-search— Search products in catalog
"""

import hmac
import logging
import sys
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
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


async def require_secret(x_waku_secret: str = Header(default="")) -> None:
    """Gate /ai/* on a shared secret. No-op when AI_SERVICE_SECRET is unset (dev);
    when set, the backend must send a matching X-Waku-Secret header."""
    secret = settings.ai_service_secret
    if secret and not hmac.compare_digest(x_waku_secret, secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ──────────────────────────────────────────────
#  Request/Response models
# ──────────────────────────────────────────────

class ReplyRequest(BaseModel):
    business_context: Optional[dict] = Field(default=None, description="Business info (store_name, owner_name, etc.)")
    message_history: list[dict] = Field(default_factory=list, description="Previous messages [{'role','content'}]")
    incoming_message: str = Field(..., description="Customer's latest message")
    catalog: Optional[list[dict]] = Field(default=None, description="Product catalog [{name, price, stock}]")
    session_id: str = Field(default="default", description="Conversation/session identifier")
    customer: Optional[dict] = Field(default=None, description="Personalisation card {name, usual_items, ...}")
    business_type: Optional[str] = Field(default="warung", description="warung | salon | wedding")


class ReplyResponse(BaseModel):
    reply: str = Field(..., description="AI-generated reply in Bahasa Indonesia")
    intent: str = Field(default="UNKNOWN", description="Detected intent")
    session_id: str = Field(default="default")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    order: Optional[dict] = Field(default=None, description="Finalised order on close; null otherwise")
    booking: Optional[dict] = Field(default=None, description="Finalised booking on close; null otherwise")


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


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., description="Texts to embed")


class EmbedResponse(BaseModel):
    vectors: list[list[float]] = Field(default_factory=list)


class MatchImageRequest(BaseModel):
    image_b64: str
    mime_type: str = "image/jpeg"
    caption: str = ""
    catalog: list[dict] = Field(default_factory=list)
    business_type: str = "warung"


class MatchImageResponse(BaseModel):
    matched: bool = False
    product_name: str = ""
    price: float = 0.0
    reply: str = ""


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


@app.post("/ai/reply", response_model=ReplyResponse, dependencies=[Depends(require_secret)])
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
            customer=request.customer,
            business_type=request.business_type,
        )

        # Get the intent from the last analysis (stored in conv)
        from nlu import analyze_message
        catalog_names = []
        if request.catalog:
            catalog_names = [item.get("name", "") for item in request.catalog]
        analysis = analyze_message(request.incoming_message, catalog_items=catalog_names)

        conv = conversation_manager.get(request.session_id)
        closed = conv.closed_order if conv else None
        booking = conv.closed_booking if conv else None
        return ReplyResponse(
            reply=reply,
            intent=analysis["intent"],
            session_id=request.session_id,
            order=closed,
            booking=booking,
        )
    except Exception as e:
        logger.exception(f"Error in /ai/reply: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/extract-order", response_model=ExtractOrderResponse, dependencies=[Depends(require_secret)])
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


@app.post("/ai/summarize", dependencies=[Depends(require_secret)])
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


@app.post("/ai/catalog-search", dependencies=[Depends(require_secret)])
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


@app.post("/ai/match-image", response_model=MatchImageResponse, dependencies=[Depends(require_secret)])
async def ai_match_image(request: MatchImageRequest):
    """Match a customer-sent product image to the business catalog using a vision LLM."""
    from llm import match_image_to_catalog
    try:
        result = match_image_to_catalog(request.image_b64, request.mime_type, request.caption, request.catalog)
        return MatchImageResponse(**result)
    except Exception as e:
        logger.exception(f"Error in /ai/match-image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/embed", response_model=EmbedResponse, dependencies=[Depends(require_secret)])
async def ai_embed(request: EmbedRequest):
    """Embed texts for hybrid catalog retrieval."""
    from embeddings import embed_texts
    try:
        return EmbedResponse(vectors=embed_texts(request.texts))
    except RuntimeError as exc:
        logger.warning("Embedding unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="Embedding provider unavailable")


# ──────────────────────────────────────────────
#  Startup / Shutdown
# ──────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("Waku AI Service starting...")
    # Chat providers, in fallback order
    if settings.use_deepseek:
        logger.info(f"Chat primary: DeepSeek — {settings.deepseek_model} @ {settings.deepseek_base_url}")
    if settings.use_openai:
        label = "primary" if not settings.use_deepseek else "fallback"
        logger.info(f"Chat {label}: OpenRouter — {settings.llm_model} @ {settings.openai_base_url}")
    if settings.llm_provider != "openai":
        logger.info(f"Chat last-resort: Ollama — {settings.ollama_model} @ {settings.ollama_base_url}")
    logger.info(f"Embeddings: HuggingFace — {settings.hf_embed_model} @ {settings.hf_embed_base_url}")
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
