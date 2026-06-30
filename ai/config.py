"""Configuration for Waku AI Service — loaded from .env"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # OpenAI-compatible API (chat)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "cohere/north-mini-code:free")

    # Ollama (local LLM fallback)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")

    # Embeddings (Phase B hybrid retrieval)
    embed_model: str = os.getenv("EMBED_MODEL", "nvidia/llama-nemotron-embed-vl-1b-v2:free")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # Service
    service_port: int = int(os.getenv("AI_SERVICE_PORT", "8001"))
    # Shared secret the backend must send (X-Waku-Secret). Empty = open (dev only).
    ai_service_secret: str = os.getenv("AI_SERVICE_SECRET", "")

    # Conversation
    max_context_messages: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))

    # Which provider to prefer: "auto" (try OpenAI first, then Ollama), "openai", "ollama"
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto")

    # OpenRouter optional ranking headers
    openrouter_site_url: str = os.getenv("OPENROUTER_SITE_URL", "")
    openrouter_app_name: str = os.getenv("OPENROUTER_APP_NAME", "")

    @property
    def use_openai(self) -> bool:
        if self.llm_provider == "openai":
            return True
        if self.llm_provider == "ollama":
            return False
        # auto: use OpenAI if key is set
        return bool(self.openai_api_key.strip())

    @property
    def vision_model(self) -> str:
        """Vision model for image tasks; falls back to llm_model when unset."""
        return os.getenv("VISION_MODEL", "") or self.llm_model

    @property
    def embed_base_url(self) -> str:
        """Base URL for embedding calls; falls back to chat base URL when unset."""
        return os.getenv("EMBED_BASE_URL", "") or self.openai_base_url

    @property
    def embed_api_key(self) -> str:
        """API key for embedding calls; falls back to chat API key when unset."""
        return os.getenv("EMBED_API_KEY", "") or self.openai_api_key

    @property
    def embed_input_format(self) -> str:
        """Input format for embeddings: 'openrouter' (content-array) or 'openai' (plain strings)."""
        return os.getenv("EMBED_INPUT_FORMAT", "openai")

    @property
    def openrouter_headers(self) -> dict:
        """Optional OpenRouter ranking headers (HTTP-Referer, X-Title)."""
        h = {}
        if self.openrouter_site_url:
            h["HTTP-Referer"] = self.openrouter_site_url
        if self.openrouter_app_name:
            h["X-Title"] = self.openrouter_app_name
        return h


settings = Settings()
