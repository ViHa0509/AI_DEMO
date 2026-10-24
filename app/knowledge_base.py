"""Learning-path knowledge base: Excel loader, embeddings and the in-memory vector store.

Without PGVECTOR_CONN the app embeds data/LearningPath.xlsx into an in-memory store, so it
needs no database. The embedded index is cached on disk (keyed by the Excel file's hash) and is
pre-built in the Docker image:

    python -m app.knowledge_base      # download the embedding model and build the index
"""
import hashlib
import logging
from functools import lru_cache
from pathlib import Path

import pandas as pd
from langchain_core.documents import Document

from app.config import ROOT_DIR, settings

logger = logging.getLogger(__name__)

EXCEL_FILE = ROOT_DIR / "vectordb" / "data" / "LearningPath.xlsx"
INDEX_DIR = ROOT_DIR / ".cache"
SKIP_SHEETS = {"Template"}  # example sheet, not real data
REQUIRED_COLUMNS = {
    "Competency Area", "Skill/Knowledge", "Description",
    "Proficiency Level", "Training couse link", "Target Date",
    "Completion Date", "Notes",
}


def _cell(row, column: str) -> str:
    value = row.get(column, "")
    return "" if pd.isna(value) else str(value).strip()


METADATA_COLUMNS = {
    "proficiency_level": "Proficiency Level",
    "course_link": "Training couse link",
    "target_date": "Target Date",
    "completion_date": "Completion Date",
    "notes": "Notes",
}


def _skill_blocks(df: pd.DataFrame, sheet: str) -> list[dict]:
    """Group rows into one record per skill.

    The sheets use merged cells: only the first row of a skill carries its name, the following
    rows hold more description lines. Forward-filling the merged columns restores the grouping.
    """
    df = df.copy()
    df["Competency Area"] = df["Competency Area"].ffill().fillna(sheet)
    df["Skill/Knowledge"] = df["Skill/Knowledge"].ffill()

    blocks: list[dict] = []
    for _, row in df.iterrows():
        skill = _cell(row, "Skill/Knowledge")
        if not skill:
            continue  # rows before the first skill
        key = (_cell(row, "Competency Area"), skill)
        if not blocks or blocks[-1]["key"] != key:
            blocks.append({"key": key, "lines": [], **{k: "" for k in METADATA_COLUMNS}})
        block = blocks[-1]
        if description := _cell(row, "Description"):
            block["lines"].append(description)
        for field, column in METADATA_COLUMNS.items():
            block[field] = block[field] or _cell(row, column)
    return blocks


def load_docs_from_excel(path: Path = EXCEL_FILE) -> list[Document]:
    """Convert every skill of every sheet into a Document with detailed metadata."""
    xls = pd.ExcelFile(path)
    docs: list[Document] = []

    for sheet in xls.sheet_names:
        if sheet in SKIP_SHEETS:
            continue
        df = pd.read_excel(xls, sheet_name=sheet)
        if not REQUIRED_COLUMNS.issubset(df.columns):
            logger.warning("Skipping sheet '%s': missing required columns", sheet)
            continue

        for block in _skill_blocks(df, sheet):
            description = "\n".join(block["lines"]).strip()
            if not description:
                continue  # skip skills without any description
            competency, skill = block["key"]
            metadata = {
                "sheet": sheet,
                "competency_area": competency,
                "skill": skill,
                **{field: block[field] for field in METADATA_COLUMNS},
            }
            # Combine relevant text for embedding
            docs.append(Document(page_content=f"{skill}: {description}", metadata=metadata))

    logger.info("Loaded %d learning-path documents from %s", len(docs), path.name)
    return docs


@lru_cache(maxsize=1)
def get_embedder():
    # Deferred: importing torch / sentence-transformers takes several seconds
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def _index_file(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes() + settings.embedding_model.encode()).hexdigest()[:16]
    return INDEX_DIR / f"kb_index-{digest}.json"


@lru_cache(maxsize=1)
def get_in_memory_store():
    """Load the cached index for the current Excel file, or embed it and cache the result."""
    from langchain_core.vectorstores import InMemoryVectorStore

    index_file = _index_file(EXCEL_FILE)
    if index_file.exists():
        logger.info("Loading knowledge-base index %s", index_file.name)
        return InMemoryVectorStore.load(str(index_file), get_embedder())

    store = InMemoryVectorStore.from_documents(load_docs_from_excel(), get_embedder())
    try:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        for stale in INDEX_DIR.glob("kb_index-*.json"):
            stale.unlink()
        store.dump(str(index_file))
        logger.info("Saved knowledge-base index %s", index_file.name)
    except OSError as e:
        logger.warning("Could not cache the knowledge-base index: %s", e)
    return store


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    get_in_memory_store()
