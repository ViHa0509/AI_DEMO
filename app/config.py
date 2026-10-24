"""Central configuration, read once from environment variables / .env."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM (any OpenAI-compatible endpoint: OpenAI, vLLM, LM Studio, Ollama...)
    model_name: str = os.getenv("AI_MODEL_PATH", "gpt-4o-mini")
    model_api: str | None = os.getenv("AI_MODEL_API") or None
    api_key: str = os.getenv("API_KEY") or "not-needed"
    temperature: float = float(os.getenv("AI_TEMPERATURE", "0.3"))
    max_tokens: int = int(os.getenv("AI_MAX_TOKENS", "1024"))

    # Vector store (PGVector)
    pgvector_conn: str | None = os.getenv("PGVECTOR_CONN") or None
    collection_name: str = os.getenv("PGVECTOR_COLLECTION", "langchain_pg_embedding")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
    retriever_k: int = int(os.getenv("RETRIEVER_K", "5"))
    # 0 = plain top-k similarity; > 0 = drop results below this relevance score (0..1)
    retriever_score_threshold: float = float(os.getenv("RETRIEVER_SCORE_THRESHOLD", "0"))

    # External tools
    tavily_api_key: str | None = os.getenv("TAVILY_API_KEY") or None
    virustotal_api_key: str | None = os.getenv("VIRUSTOTAL_API_KEY") or None
    # When no VirusTotal key is configured: True = refuse to crawl, False = crawl without scan
    require_url_scan: bool = _bool("REQUIRE_URL_SCAN", False)
    http_timeout: int = int(os.getenv("HTTP_TIMEOUT", "15"))

    prompt_file: Path = ROOT_DIR / "app" / "prompt.yaml"


settings = Settings()
