"""Configuration for Waku AI Service — loaded from .env"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # OpenAI-compatible API
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Ollama (local LLM fallback)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")

    # Embeddings (Phase B hybrid retrieval)
    embed_model: str = os.getenv("EMBED_MODEL", "text-embedding-3-small")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # Service
    service_port: int = int(os.getenv("AI_SERVICE_PORT", "8001"))
    # Shared secret the backend must send (X-Waku-Secret). Empty = open (dev only).
    ai_service_secret: str = os.getenv("AI_SERVICE_SECRET", "")

    # Conversation
    max_context_messages: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))

    # Which provider to prefer: "auto" (try OpenAI first, then Ollama), "openai", "ollama"
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto")

    @property
    def use_openai(self) -> bool:
        if self.llm_provider == "openai":
            return True
        if self.llm_provider == "ollama":
            return False
        # auto: use OpenAI if key is set
        return bool(self.openai_api_key.strip())


settings = Settings()
