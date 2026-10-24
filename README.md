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
  knowledge_base.py  Excel loader, embeddings, in-memory vector store (no DB needed)
  retriever.py     retriever: PGVector if configured, otherwise in-memory
  crawler.py       page fetching + article extraction (with SSRF protection)
  url_scanner.py   VirusTotal URL safety check
  security.py      password login (signed tokens) and rate limiting
  graph.py         LangGraph state, agents and workflow
  server.py        FastAPI backend: streaming chat API + serves the web UI
web/               web UI (HTML/CSS/JS, no build step)
tests/             pytest suite (no network, fake LLM)
deploy/            Hugging Face Spaces deploy script
.github/workflows/ CI/CD: tests → Docker smoke test → deploy
Dockerfile
vectordb/
  docker-compose.yml   Postgres + pgvector + pgAdmin (optional)
  data/LearningPath.xlsx
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

# 3. (Optional) use PGVector instead of the built-in in-memory knowledge base
docker compose -f vectordb/docker-compose.yml up -d
python -m vectordb.vectorstore.store      # then set PGVECTOR_CONN in .env

# 4. Run the web UI
python -m app.server              # open http://localhost:8000
#    or the terminal chat
python main.py                    # add --graph to export graph.png
```

## Configuration

| Variable | Purpose |
|---|---|
| `AI_MODEL_PATH`, `AI_MODEL_API`, `API_KEY` | Model name, OpenAI-compatible base URL (empty = OpenAI), key |
| `PGVECTOR_CONN`, `PGVECTOR_COLLECTION` | Optional PGVector store for the **adviser** agent (default: in-memory) |
| `APP_PASSWORD`, `RATE_LIMIT_PER_MINUTE` | Access password for the web UI/API and per-client chat limit |
| `TAVILY_API_KEY` | Enables the **search** agent |
| `VIRUSTOTAL_API_KEY` | Scans URLs before the **crawl** agent opens them |
| `REQUIRE_URL_SCAN` | `true` = refuse to crawl when no VirusTotal key is set |
| `LANGSMITH_*` | Optional LangSmith tracing |

Agents whose keys are missing still answer with a clear message instead of crashing; the sidebar of the web UI shows which features are configured.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Model name, configured features, whether a password is required |
| `POST` | `/api/login` | `{"password"}` → bearer token (only when `APP_PASSWORD` is set) |
| `POST` | `/api/chat` | `{"message", "thread_id"}`, Server-Sent Events: `route`, `token`, `final`, `error`, `done` |
| `GET` | `/api/threads/{id}/messages` | Conversation held in server memory |
| `DELETE` | `/api/threads/{id}` | Forget a conversation |

Conversation memory uses LangGraph's in-memory checkpointer, so it resets when the server restarts. The browser keeps its own copy of the chat list.

## Tests and deployment

```bash
pip install -r requirements-dev.txt
pytest -q
```

Every push runs the tests and a Docker smoke test on GitHub Actions; pushes to `main` deploy to Hugging Face Spaces. Setup steps are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

See [docs/HANDOFF.md](docs/HANDOFF.md) for project status, known issues and next steps.
