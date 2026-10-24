"""Retriever over the learning-path knowledge base (PGVector if configured, otherwise in-memory)."""
import json
import logging
from functools import lru_cache

from app.config import settings
from app.knowledge_base import get_embedder, get_in_memory_store

logger = logging.getLogger(__name__)


def knowledge_backend() -> str:
    return "pgvector" if settings.pgvector_conn else "in-memory"


@lru_cache(maxsize=1)
def get_retriever():
    if settings.pgvector_conn:
        from langchain_community.vectorstores import PGVector

        vectorstore = PGVector(
            collection_name=settings.collection_name,
            connection_string=settings.pgvector_conn,
            embedding_function=get_embedder(),
        )
    else:
        vectorstore = get_in_memory_store()

    if settings.retriever_score_threshold > 0:
        return vectorstore.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"k": settings.retriever_k, "score_threshold": settings.retriever_score_threshold},
        )
    return vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": settings.retriever_k})


def lookup_learning_paths(query: str) -> tuple[str, list[dict]]:
    """Return (json context for the LLM, list of metadata records) for a query."""
    try:
        results = get_retriever().invoke(query)
    except Exception as e:
        logger.error("Vector lookup failed: %s", e)
        return "No learning-path data available (knowledge base unreachable).", []

    if not results:
        logger.info("No vector results for query")
        return "No relevant learning-path data found.", []

    records = [doc.metadata for doc in results]
    logger.info("Found %d learning-path records", len(records))
    return json.dumps(records, indent=2, ensure_ascii=False), records
