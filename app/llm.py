"""Shared chat model instance."""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.model_name,
        base_url=settings.model_api,
        api_key=settings.api_key,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=60,
        streaming=True,  # tokens are forwarded to the web UI as they arrive
    )
