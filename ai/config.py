"""Configuration for Waku AI Service — loaded from .env"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Chat primary: DeepSeek (OpenAI-compatible)
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    # Chat/embed fallback: OpenRouter (OpenAI-compatible). Also used for vision.
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "cohere/north-mini-code:free")

    # Ollama (local LLM fallback)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")

    # Embeddings: HuggingFace Inference only (feature-extraction). Pinned to one
    # provider — cross-provider fallback breaks vector-space compatibility.
    hf_api_key: str = os.getenv("HF_API_KEY", "")
    hf_embed_model: str = os.getenv("HF_EMBED_MODEL", "google/embeddinggemma-300m")
    hf_embed_base_url: str = os.getenv("HF_EMBED_BASE_URL", "https://router.huggingface.co")

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
    def use_deepseek(self) -> bool:
        """Primary chat provider — used when a DeepSeek key is set and Ollama isn't forced."""
        return self.llm_provider != "ollama" and bool(self.deepseek_api_key.strip())

    @property
    def use_openai(self) -> bool:
        if self.llm_provider == "openai":
            return True
        if self.llm_provider == "ollama":
            return False
        # auto: use OpenAI-compatible fallback (OpenRouter) if key is set
        return bool(self.openai_api_key.strip())

    @property
    def vision_model(self) -> str:
        """OpenRouter vision model (fallback); falls back to llm_model when unset."""
        return os.getenv("VISION_MODEL", "") or self.llm_model

    @property
    def deepseek_vision_model(self) -> str:
        """DeepSeek vision model (primary); falls back to deepseek_model when unset."""
        return os.getenv("DEEPSEEK_VISION_MODEL", "") or self.deepseek_model

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
