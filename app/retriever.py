"""PGVector retriever over the learning-path knowledge base."""
import json
import logging
from functools import lru_cache

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_retriever():
    # Heavy imports (torch / sentence-transformers) are deferred until first use
    from langchain_community.vectorstores import PGVector
    from langchain_huggingface import HuggingFaceEmbeddings

    if not settings.pgvector_conn:
        raise RuntimeError("PGVECTOR_CONN is not configured")

    embedder = HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    vectorstore = PGVector(
        collection_name=settings.collection_name,
        connection_string=settings.pgvector_conn,
        embedding_function=embedder,
    )
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
