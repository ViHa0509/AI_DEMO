import os
from dotenv import load_dotenv
import pandas as pd
from langchain_core.documents import Document
from langchain_community.vectorstores import PGVector
from embedding.embedder import get_embedder

# Load .env
load_dotenv()

# Configs
CONNECTION_STRING = os.getenv("PGVECTOR_CONN")
COLLECTION_NAME = "rag_learning_path"
EXCEL_FILE = "data/LearningPath.xlsx"
TABLE_NAME = "langchain_pg_embedding"  # PGVector table

def load_docs_from_excel(path: str) -> list[Document]:
    """
    Reads each sheet of the Excel file and converts rows into
    langchain_core.documents.Document objects with detailed metadata.
    """
    xls = pd.ExcelFile(path)
    docs: list[Document] = []

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)

        required_cols = {
            "Competency Area", "Skill/Knowledge", "Description",
            "Proficiency Level", "Training couse link", "Target Date",
            "Completion Date", "Notes"
        }

        if not required_cols.issubset(df.columns):
            print(f"⚠️ Skipping sheet '{sheet}' — missing required columns.")
            continue

        for _, row in df.iterrows():
            competency = str(row.get("Competency Area", "")).strip()
            skill = str(row.get("Skill/Knowledge", "")).strip()
            description = str(row.get("Description", "")).strip()

            if not (competency and skill and description):
                continue  # skip incomplete rows

            # 👇 Combine relevant text for embedding
            content = f"{skill}: {description}"

            metadata = {
                "sheet": sheet,
                "competency_area": competency,
                "skill": skill,
                "proficiency_level": str(row.get("Proficiency Level", "")).strip(),
                "course_link": str(row.get("Training couse link", "")).strip(),
                "target_date": str(row.get("Target Date", "")).strip(),
                "completion_date": str(row.get("Completion Date", "")).strip(),
                "notes": str(row.get("Notes", "")).strip()
            }

            docs.append(Document(page_content=content, metadata=metadata))

    print(f"📄 Loaded {len(docs)} documents from Excel")
    return docs


def create_vectorstore():
    """
    Creates (or reuses) a PGVector table and ingests documents+embeddings.
    """
    docs = load_docs_from_excel(EXCEL_FILE)
    embedder = get_embedder()
    return PGVector.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=TABLE_NAME , # table name in Postgres
        connection_string=CONNECTION_STRING,
        pre_delete_collection=True # drop & recreate for fresh ingest
    )
    # print(f"✅ Ingested {len(docs)} documents into `{TABLE_NAME}`")
