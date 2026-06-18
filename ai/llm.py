"""LLM Integration for Waku AI — Supports OpenAI-compatible API + Ollama fallback."""

import json
import logging
import time
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

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
            return data["choices"][0]["message"]["content"]
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

    response = None

    # Try OpenAI first if configured and allowed
    if settings.use_openai:
        response = call_openai(full_messages, temperature=temperature, max_tokens=max_tokens)
        if response:
            logger.info("Used OpenAI-compatible API")
            return response

    # Fallback to Ollama
    try:
        response = call_ollama(full_messages, temperature=temperature, max_tokens=max_tokens)
        if response:
            logger.info("Used Ollama")
            return response
    except Exception as e:
        logger.warning(f"Ollama call failed: {e}")

    # Ultimate fallback: rule-based
    logger.warning(f"LLM unavailable, using fallback for intent={intent}")
    return get_fallback_response(intent)
