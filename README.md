# AI Learning Assistant

A multi-agent chatbot built with **LangGraph**. Each message is classified, then routed to the agent best suited to answer it. It ships with a web UI (streaming answers, chat history, light/dark theme) and a terminal chat.

```
START ─► classifier ─┬─► adviser       learning paths from the PGVector knowledge base (RAG)
                     ├─► search        up-to-date answers from Tavily web search
                     ├─► crawl         VirusTotal scan, then fetch and summarise a web page
                     └─► conversation  small talk / general questions
                                       ─► END
```

## Project structure

```
app/
  config.py        settings read from .env
  prompts.py       loads prompt.yaml
  prompt.yaml      all prompt templates
  llm.py           shared ChatOpenAI client (any OpenAI-compatible endpoint)
  retriever.py     PGVector retriever (learning paths)
  crawler.py       page fetching + article extraction (with SSRF protection)
  url_scanner.py   VirusTotal URL safety check
  graph.py         LangGraph state, agents and workflow
  server.py        FastAPI backend: streaming chat API + serves the web UI
web/               web UI (HTML/CSS/JS, no build step)
vectordb/
  docker-compose.yml   Postgres + pgvector + pgAdmin
  data/LearningPath.xlsx
  embedding/embedder.py
  vectorstore/store.py  ingests the Excel file into PGVector
main.py            terminal chat
```

## Quick start

```bash
# 1. Install
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

# 2. Configure
copy .env.example .env            # macOS/Linux: cp .env.example .env
#    then fill in AI_MODEL_PATH / AI_MODEL_API / API_KEY and the optional keys

# 3. (Optional) start the vector DB and ingest the learning paths
cd vectordb
docker compose up -d
python -m vectorstore.store
cd ..

# 4. Run the web UI
python -m app.server              # open http://localhost:8000
#    or the terminal chat
python main.py                    # add --graph to export graph.png
```

## Configuration

| Variable | Purpose |
|---|---|
| `AI_MODEL_PATH`, `AI_MODEL_API`, `API_KEY` | Model name, OpenAI-compatible base URL (empty = OpenAI), key |
| `PGVECTOR_CONN`, `PGVECTOR_COLLECTION` | Vector store used by the **adviser** agent |
| `TAVILY_API_KEY` | Enables the **search** agent |
| `VIRUSTOTAL_API_KEY` | Scans URLs before the **crawl** agent opens them |
| `REQUIRE_URL_SCAN` | `true` = refuse to crawl when no VirusTotal key is set |
| `LANGSMITH_*` | Optional LangSmith tracing |

Agents whose keys are missing still answer with a clear message instead of crashing; the sidebar of the web UI shows which features are configured.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Model name and configured features |
| `POST` | `/api/chat` | `{"message", "thread_id"}`, Server-Sent Events: `route`, `token`, `final`, `error`, `done` |
| `GET` | `/api/threads/{id}/messages` | Conversation held in server memory |
| `DELETE` | `/api/threads/{id}` | Forget a conversation |

Conversation memory uses LangGraph's in-memory checkpointer, so it resets when the server restarts. The browser keeps its own copy of the chat list.

See [docs/HANDOFF.md](docs/HANDOFF.md) for project status, known issues and next steps.
