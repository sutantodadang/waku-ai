"""LLM Integration for Waku AI — Supports OpenAI-compatible API + Ollama fallback."""

import json
import logging
import re
import time
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# ──────────────────────────────────────────────
#  System prompt — Indonesian UMKM style
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """Kamu adalah **Waku**, asisten AI untuk UMKM (usaha mikro, kecil, dan menengah) di Indonesia. Tugasmu membantu pemilik usaha melayani pelanggan di WhatsApp.

GAYA BERBICARA:
- Gunakan bahasa Indonesia yang hangat, sopan, dan ramah
- Panggil pelanggan dengan "Kak" (contoh: "Baik Kak, ada yang bisa Waku bantu?")
- Jawab singkat, padat, jelas — tidak bertele-tele
- Gunakan bahasa yang natural seperti orang ngobrol di WA
- Bisa pakai slang ringan seperti "ditunggu ya Kak", "siap Kak", "mantap"
- Jangan gunakan bahasa formal/kaku

KAMU BISA:
- Menerima pesanan dari pelanggan
- Menjelaskan menu/catalog produk
- Mengecek stok (bilang "stok tersedia" atau "stok habis" saja)
- Menjawab pertanyaan harga
- Menangani keluhan dengan empati
- Membantu pembayaran (transfer, COD)

KETERBATASAN:
- Kamu hanya asisten — jika ada masalah kompleks, arahkan ke pemilik toko
- Tidak bisa memproses pembayaran sungguhan
- Tidak bisa menjanjikan diskon di luar kebijakan toko

Contoh jawaban yang baik:
- "Halo Kak! Selamat datang di Waku Shop 👋 Ada yang bisa Waku bantu hari ini?"
- "Baik Kak, Waku catat pesanannya: 2 Nasi Goreng + 1 Es Teh Manis. Ada lagi Kak?"
- "Maaf Kak, untuk stok Ayam Bakar memang sedang habis. Tapi ada pilihan lain seperti Ayam Goreng atau Ayam Rica, Kak tertarik?"
- "Siap Kak! Pesanannya sudah Waku teruskan ke pemilik toko ya. Terima kasih sudah pesan di Waku Shop 😊"
"""

# ──────────────────────────────────────────────
#  Rule-based fallback responses
# ──────────────────────────────────────────────

FALLBACK_RESPONSES = {
    "GREETING": "Halo Kak! Selamat datang di Waku Shop 👋 Ada yang bisa Waku bantu hari ini?",
    "ORDER": "Baik Kak, Waku catat pesanannya dulu ya. Bisa sebutkan apa saja yang Kakak mau pesan?",
    "INQUIRY_PRICE": "Untuk info harga, Kakak bisa lihat di katalog kami atau bisa juga tanya langsung ke pemilik toko ya Kak 😊",
    "INQUIRY_STOCK": "Stok produk yang Kakak tanyakan masih tersedia Kak! Ada yang mau dipesan?",
    "COMPLAINT": "Maaf Kak atas ketidaknyamanannya 🙏 Waku akan sampaikan keluhan Kakak ke pemilik toko ya, tunggu sebentar ya.",
    "PAYMENT": "Kakak bisa bayar via transfer ke rekening yang tertera atau COD (bayar di tempat). Ada yang ingin ditanyakan Kak?",
    "CLOSING": "Terima kasih Kak sudah menghubungi Waku Shop! Kalau ada perlu, bilang aja lagi ya 😊",
    "UNKNOWN": "Halo Kak! Maaf, Waku kurang paham maksudnya. Bisa dijelaskan lagi? Waku siap bantu 😊",
}


def get_fallback_response(intent: str) -> str:
    """Return a rule-based fallback response for a given intent."""
    return FALLBACK_RESPONSES.get(intent, FALLBACK_RESPONSES["UNKNOWN"])


# ──────────────────────────────────────────────
#  Content extraction helper
# ──────────────────────────────────────────────

def _extract_content(data: dict) -> Optional[str]:
    """Assistant text from an OpenAI-compatible chat response. Falls back to
    `reasoning_content` (stripped of <think> blocks) for reasoning models
    (e.g. nemotron-nano) that leave `content` empty."""
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    content = msg.get("content")
    if content and content.strip():
        return content.strip()
    reasoning = msg.get("reasoning_content")
    if reasoning and reasoning.strip():
        cleaned = _THINK_RE.sub("", reasoning).strip()
        if cleaned:
            return cleaned
    return None


# ──────────────────────────────────────────────
#  OpenAI-compatible API caller
# ──────────────────────────────────────────────

def call_openai(messages: list[dict], model: Optional[str] = None, temperature: float = 0.7,
                max_tokens: int = 1024) -> Optional[str]:
    """Call an OpenAI-compatible API and return the response content."""
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set, skipping OpenAI call")
        return None

    model = model or settings.llm_model
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = _extract_content(data)
            if content:
                return content
            logger.warning("OpenAI 200 but no usable content; raw=%.300s", json.dumps(data)[:300])
            return None
    except httpx.HTTPStatusError as e:
        logger.error(f"OpenAI API HTTP error: {e.response.status_code} {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"OpenAI API request failed: {e}")
    except (KeyError, json.JSONDecodeError, IndexError) as e:
        logger.error(f"OpenAI API response parse error: {e}")

    return None


# ──────────────────────────────────────────────
#  Ollama caller
# ──────────────────────────────────────────────

def call_ollama(messages: list[dict], model: Optional[str] = None, temperature: float = 0.7,
                max_tokens: int = 1024) -> Optional[str]:
    """Call a local Ollama instance."""
    model = model or settings.ollama_model
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                url,
                json={
                    "model": model,
                    "messages": messages,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]
    except httpx.HTTPStatusError as e:
        logger.error(f"Ollama HTTP error: {e.response.status_code} {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Ollama request failed: {e}")
    except (KeyError, json.JSONDecodeError) as e:
        logger.error(f"Ollama response parse error: {e}")

    return None


# ──────────────────────────────────────────────
#  Main LLM call with automatic fallback
# ──────────────────────────────────────────────

def ask_llm(messages: list[dict], intent: str = "UNKNOWN",
            system_prompt: Optional[str] = None,
            temperature: float = 0.7, max_tokens: int = 1024) -> str:
    """
    Send messages to the LLM. Tries OpenAI first (if configured), then Ollama,
    then falls back to rule-based responses.

    Args:
        messages: Conversation messages (without system prompt — it's prepended)
        intent: Intent string for fallback when LLM is unavailable
        system_prompt: Optional custom system prompt (defaults to SYSTEM_PROMPT)
        temperature: LLM temperature
        max_tokens: Max tokens in response

    Returns:
        Response string from LLM or fallback
    """
    full_messages = [{"role": "system", "content": system_prompt or SYSTEM_PROMPT}]
    full_messages.extend(messages)
    provider = settings.llm_provider

    # OpenAI-compatible path
    if settings.use_openai:
        response = call_openai(full_messages, temperature=temperature, max_tokens=max_tokens)
        if response and response.strip():
            logger.info("Used OpenAI-compatible API")
            return response
        if provider == "openai":
            # Explicitly OpenAI-only: do NOT fall back to Ollama.
            logger.warning(f"OpenAI returned no usable content; rule fallback for intent={intent}")
            return get_fallback_response(intent)

    # Ollama path (auto or ollama only — never when provider is openai)
    if provider != "openai":
        try:
            response = call_ollama(full_messages, temperature=temperature, max_tokens=max_tokens)
            if response and response.strip():
                logger.info("Used Ollama")
                return response
        except Exception as e:
            logger.warning(f"Ollama call failed: {e}")

    logger.warning(f"LLM unavailable, using fallback for intent={intent}")
    return get_fallback_response(intent)


# ──────────────────────────────────────────────
#  Vision: match image to catalog product
# ──────────────────────────────────────────────

def match_image_to_catalog(image_b64: str, mime_type: str, caption: str, catalog: list[dict]) -> dict:
    """Ask a vision LLM which catalog product an image shows. Degrades to
    matched=False with an ask-to-confirm reply when no vision model is available."""

    _not_matched_reply = (
        "Waku terima gambarnya Kak 🙏 Tapi Waku belum yakin ini produk yang mana. "
        "Boleh sebutkan nama produknya ya?"
    )

    names = [p.get("name", "") for p in catalog if p.get("name")]

    if not names:
        return {"matched": False, "product_name": "", "price": 0.0, "reply": _not_matched_reply}

    # Normalize to data URI
    if image_b64.startswith("data:"):
        data_uri = image_b64
    else:
        data_uri = f"data:{mime_type};base64,{image_b64}"

    messages = [
        {
            "role": "system",
            "content": (
                "Kamu adalah Waku, asisten AI untuk UMKM Indonesia. "
                "Tugasmu mengidentifikasi produk dalam foto berdasarkan daftar katalog yang diberikan. "
                "Jawab dengan TEPAT salah satu nama produk dari daftar, atau kata NONE jika tidak ada yang cocok."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Daftar produk: {', '.join(names)}. "
                        f"Caption pelanggan: '{caption}'. "
                        "Produk mana yang ada di foto ini? Jawab persis salah satu nama dari daftar, atau NONE."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                },
            ],
        },
    ]

    answer = call_openai(messages, max_tokens=200, temperature=0.0)

    if not answer or not answer.strip():
        logger.warning("match_image_to_catalog: no answer from LLM (text-only model?)")
        return {"matched": False, "product_name": "", "price": 0.0, "reply": _not_matched_reply}

    answer_stripped = answer.strip()

    # Try to find a matching catalog product
    matched_product = None
    answer_lower = answer_stripped.lower()

    # Exact case-insensitive match first
    for p in catalog:
        if p.get("name", "").lower() == answer_lower:
            matched_product = p
            break

    # Substring match fallback
    if matched_product is None:
        for p in catalog:
            name_lower = p.get("name", "").lower()
            if name_lower and (name_lower in answer_lower or answer_lower in name_lower):
                matched_product = p
                break

    # NONE or no match
    if matched_product is None or "none" in answer_lower:
        return {"matched": False, "product_name": "", "price": 0.0, "reply": _not_matched_reply}

    name = matched_product.get("name", "")
    price = float(matched_product.get("price", 0) or 0)
    price_str = f"Rp{int(price):,}".replace(",", ".")
    reply = f"Ini *{name}* ya Kak? Harganya {price_str}. Mau Waku catat pesanannya? 🙏"

    return {"matched": True, "product_name": name, "price": price, "reply": reply}
