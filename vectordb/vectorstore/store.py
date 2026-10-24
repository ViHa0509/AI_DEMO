"""Ingest data/LearningPath.xlsx into PGVector.

Run from the vectordb/ folder:  python -m vectorstore.store
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document

from embedding.embedder import get_embedder

VECTORDB_DIR = Path(__file__).resolve().parent.parent
load_dotenv(VECTORDB_DIR.parent / ".env")

# Configs
CONNECTION_STRING = os.getenv("PGVECTOR_CONN")
# Must match PGVECTOR_COLLECTION used by the chatbot (app/config.py)
COLLECTION_NAME = os.getenv("PGVECTOR_COLLECTION", "langchain_pg_embedding")
EXCEL_FILE = VECTORDB_DIR / "data" / "LearningPath.xlsx"

REQUIRED_COLUMNS = {
    "Competency Area", "Skill/Knowledge", "Description",
    "Proficiency Level", "Training couse link", "Target Date",
    "Completion Date", "Notes",
}


def _cell(row, column: str) -> str:
    value = row.get(column, "")
    return "" if pd.isna(value) else str(value).strip()


def load_docs_from_excel(path: Path) -> list[Document]:
    """
    Reads each sheet of the Excel file and converts rows into
    langchain_core.documents.Document objects with detailed metadata.
    """
    xls = pd.ExcelFile(path)
    docs: list[Document] = []

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)

        if not REQUIRED_COLUMNS.issubset(df.columns):
            print(f"⚠️ Skipping sheet '{sheet}' — missing required columns.")
            continue

        for _, row in df.iterrows():
            competency = _cell(row, "Competency Area")
            skill = _cell(row, "Skill/Knowledge")
            description = _cell(row, "Description")

            if not (competency and skill and description):
                continue  # skip incomplete rows

            metadata = {
                "sheet": sheet,
                "competency_area": competency,
                "skill": skill,
                "proficiency_level": _cell(row, "Proficiency Level"),
                "course_link": _cell(row, "Training couse link"),
                "target_date": _cell(row, "Target Date"),
                "completion_date": _cell(row, "Completion Date"),
                "notes": _cell(row, "Notes"),
            }
            # Combine relevant text for embedding
            docs.append(Document(page_content=f"{skill}: {description}", metadata=metadata))

    print(f"📄 Loaded {len(docs)} documents from Excel")
    return docs


def create_vectorstore() -> PGVector:
    """
    Creates (or recreates) the PGVector collection and ingests documents+embeddings.
    """
    if not CONNECTION_STRING:
        raise RuntimeError("PGVECTOR_CONN is not set in .env")

    docs = load_docs_from_excel(EXCEL_FILE)
    store = PGVector.from_documents(
        documents=docs,
        embedding=get_embedder(),
        collection_name=COLLECTION_NAME,
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True,  # drop & recreate for fresh ingest
    )
    print(f"✅ Ingested {len(docs)} documents into collection `{COLLECTION_NAME}`")
    return store


if __name__ == "__main__":
    create_vectorstore()
