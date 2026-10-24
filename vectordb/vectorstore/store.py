"""Ingest data/LearningPath.xlsx into PGVector (only needed when PGVECTOR_CONN is used).

Run from the repository root:  python -m vectordb.vectorstore.store
"""
from langchain_community.vectorstores import PGVector

from app.config import settings
from app.knowledge_base import get_embedder, load_docs_from_excel


def create_vectorstore() -> PGVector:
    """
    Creates (or recreates) the PGVector collection and ingests documents+embeddings.
    """
    if not settings.pgvector_conn:
        raise RuntimeError("PGVECTOR_CONN is not set in .env")

    docs = load_docs_from_excel()
    store = PGVector.from_documents(
        documents=docs,
        embedding=get_embedder(),
        collection_name=settings.collection_name,
        connection_string=settings.pgvector_conn,
        pre_delete_collection=True,  # drop & recreate for fresh ingest
    )
    print(f"✅ Ingested {len(docs)} documents into collection `{settings.collection_name}`")
    return store


if __name__ == "__main__":
    create_vectorstore()
