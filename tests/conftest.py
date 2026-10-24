import os
import sys
from pathlib import Path

import pytest

# Isolate tests from any local .env: load_dotenv never overrides variables that already exist
for name in ("PGVECTOR_CONN", "TAVILY_API_KEY", "VIRUSTOTAL_API_KEY", "APP_PASSWORD", "APP_SECRET", "LANGSMITH_API_KEY"):
    os.environ[name] = ""
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["API_KEY"] = "test"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.language_models.fake_chat_models import FakeListChatModel  # noqa: E402

from app import graph as graph_module  # noqa: E402


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the real LLM: the first answer goes to the classifier, the next to the agent."""

    def install(*responses: str) -> FakeListChatModel:
        llm = FakeListChatModel(responses=list(responses))
        monkeypatch.setattr(graph_module, "get_llm", lambda: llm)
        return llm

    return install
