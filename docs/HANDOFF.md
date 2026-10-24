# Handoff: AI Learning Assistant (web UI + LangGraph refactor)

_Last updated: 2026-10-24_

## TL;DR

- Branch **`langgraph-ui`** (created from `origin/langgraph`), pushed to `origin`. No PR yet.
- The `langgraph` branch did not run as it was: every message crashed in the graph, and every crawl crashed in the URL scanner. Both are fixed.
- Code was split into an `app/` package, and a web UI (FastAPI + plain HTML/CSS/JS, streaming answers) was added.
- **Deployment:** Dockerfile + GitHub Actions (tests → Docker smoke test → deploy to Hugging Face Spaces), password login and rate limiting. No database needed: the knowledge base is in memory. Setup: [DEPLOYMENT.md](DEPLOYMENT.md).
- **Action required:** real API keys are still in the git history of the **public** GitHub repo. Rotate them (see [Security](#security)).
- Verified against a mock LLM and fake models only. A real OpenAI key, Tavily and VirusTotal have **not** been tested yet.

## Current status

| Area | Status |
|---|---|
| Graph routing (classifier → 4 agents) | ✅ Tested with a mock OpenAI-compatible LLM |
| Web UI (streaming, history, themes, mobile) | ✅ Tested in headless Edge |
| Terminal chat (`main.py`) | ✅ Tested |
| Crawl agent + SSRF guard | ✅ Tested on thehackernews.com, example.com, 127.0.0.1 (blocked) |
| Knowledge base loader (Excel → documents) | ✅ Unit-tested; merged cells now handled (378 skills; the AI sheet was previously dropped entirely) |
| Adviser agent (in-memory RAG) | ⚠️ Embedding not run locally: torch is blocked on this laptop (see below). Covered by the CI Docker build |
| Adviser agent (PGVector) | ⚠️ Not tested: no database available; now optional |
| Password login + rate limit | ✅ Unit-tested and driven in the browser |
| Docker image / deploy | ⚠️ Not built locally (no Docker here). CI builds and smoke-tests it; deploy needs `HF_TOKEN` |
| Search agent (Tavily) | ⚠️ Not tested: no API key |
| URL scan (VirusTotal) | ⚠️ Not tested: no API key; rewritten against the v3 API docs |
| Real LLM | ❌ Waiting for the OpenAI key (to be added as GitHub secret `OPENAI_API_KEY`) |

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # set AI_MODEL_API to the server that hosts phi-4-mini, plus API_KEY
python -m app.server            # http://localhost:8000
python main.py                  # terminal chat (add --graph to export graph.png)
pytest -q                       # after: pip install -r requirements-dev.txt
```

PGVector (optional; without it the adviser uses the in-memory knowledge base):

```bash
docker compose -f vectordb/docker-compose.yml up -d   # Postgres+pgvector on 5433, pgAdmin on 8080
python -m vectordb.vectorstore.store                  # ingest data/LearningPath.xlsx
```

### Known machine-specific blocker (Windows Application Control)

On the dev laptop used for this work, Windows Application Control blocks the native DLLs of `xxhash`, `ormsgpack`, `jiter` and `msgpack` (and very likely torch). LangGraph, LangSmith and the OpenAI SDK import these, so the app fails at import with `DLL load failed ... An Application Control policy has blocked this file`.

- For testing, pure-Python stand-ins were put on `PYTHONPATH` from a temporary folder. They are **not** part of the repo and must not be used in production.
- Proper fix: ask IT to allow these packages, or run the app in Docker, WSL or on a server.

## Architecture

```
START ─► classifier ─┬─► adviser       PGVector learning paths (RAG)
                     ├─► search        Tavily results, summarised with citations
                     ├─► crawl         VirusTotal scan → fetch → extract → summarise
                     └─► conversation  small talk
                                       ─► END
```

| File | Responsibility |
|---|---|
| `app/config.py` | All settings from `.env` (single `settings` object) |
| `app/prompt.yaml`, `app/prompts.py` | Prompt templates and loader |
| `app/llm.py` | Cached `ChatOpenAI` (any OpenAI-compatible endpoint, streaming on) |
| `app/knowledge_base.py` | Excel → documents (merged cells handled), embeddings, cached in-memory index |
| `app/retriever.py` | PGVector if `PGVECTOR_CONN` is set, otherwise the in-memory store |
| `app/security.py` | `APP_PASSWORD` login with HMAC-signed tokens, per-client rate limiter |
| `Dockerfile`, `deploy/`, `.github/workflows/ci-cd.yml` | Container, HF Spaces deploy script, CI/CD pipeline |
| `tests/` | 32 pytest tests, no network (fake LLM) |
| `app/crawler.py` | Fetch + extraction (Blogger-specific first, then generic), SSRF guard |
| `app/url_scanner.py` | VirusTotal: cached report first, then submit + poll |
| `app/graph.py` | `State`, classifier (LLM + keyword fallback), agents, `build_graph()` |
| `app/server.py` | FastAPI: SSE chat API, thread memory endpoints, serves `web/` |
| `web/` | UI: `index.html`, `styles.css`, `app.js` (no build step, libs from cdnjs) |
| `main.py` | Terminal chat |
| `vectordb/vectorstore/store.py` | Excel → PGVector ingestion |

### Design decisions

- **Memory:** LangGraph `MemorySaver` keyed by `thread_id`. It is in-process, so it resets on restart. The browser keeps its own chat list in `localStorage`. To make memory survive restarts, switch to `langgraph-checkpoint-postgres` (the same Postgres can be reused).
- **Streaming:** `graph.stream(stream_mode=["updates", "messages"])`. Only tokens from agent nodes are forwarded, never the classifier's. A `final` event always carries the authoritative full text.
- **Graceful degradation:** an agent whose key or DB is missing answers with a clear message instead of crashing. `/api/health` reports configured features, and the UI sidebar shows them.
- **Crawl safety:** private, loopback and link-local addresses are refused. The VirusTotal scan runs only when `VIRUSTOTAL_API_KEY` is set; `REQUIRE_URL_SCAN=true` makes crawling refuse without it.

## Bugs fixed from `langgraph`

1. `router` node returned `{"next": ...}`, a key `State` does not have → graph error on every message. Routing now uses conditional edges straight from the classifier.
2. `classify_message` returned `None` on unexpected LLM output → added a keyword fallback.
3. `VirusTotalChecker.is_url_safe()` was called on the class (no instance) → TypeError on every crawl. The scan logic also read the analysis before it finished, so new URLs were always flagged unsafe.
4. `main.py` opened `prompt.yaml` from the repo root, but the file was in `vectordb/`.
5. Unconditional `from IPython.display import ...` (not in requirements) → crash at import.
6. `store.py` used an undefined `embeddings` variable and had no entry point.
7. Prompt `extract_data_1` asked the LLM to *invent* a fake article instead of summarising the crawled data.
8. `score_threshold` was ignored with `search_type="similarity"`; the embedding model was reloaded on every query; `requests.get` had no timeout; `crawl` crashed when a page had no `blog-posts` div.
9. `requirements.txt` was missing `python-dotenv`, `pyyaml`, `langchain-openai`, `langchain-huggingface`, `beautifulsoup4`, `tavily-python`, …

Removed as unused or duplicated: `vectordb/model/AI_model.py`, the duplicated `format_tavily_markdown`, and prompts nothing referenced.

## Security

- **Leaked keys:** commits on `origin` (e.g. before `0ec2c19` / `f6bd092`) contain a real HuggingFace token (`hf_…`), a Tavily key (`tvly-…`) and a LangSmith key (`lsv2_…`). **Rotate all three.** Deleting them in later commits does not remove them from history. Rewriting history (`git filter-repo`) is optional once they are rotated, and needs agreement from the team because it forces everyone to re-clone.
- `.env` is now untracked and ignored; `.env.example` is the template.
- `vectordb/docker-compose.yml` uses default passwords (`postgres`/`postgres`, pgAdmin `admin`). Fine locally, change before any shared deployment.
- The server binds to `127.0.0.1` by default (`HOST`/`PORT`). For public use set `APP_PASSWORD`; the deploy script refuses a public Space without it.

## API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/health` | `{status, model, features}` |
| `POST` | `/api/chat` | Body `{message, thread_id}`. SSE events: `route` → `token`* → `final` → `done` (or `error`) |
| `GET` | `/api/threads/{id}/messages` | Server-side memory for a thread |
| `DELETE` | `/api/threads/{id}` | Forget a thread |

## Suggested next steps

1. Rotate the leaked keys (blocker: the repo is public).
2. Follow [DEPLOYMENT.md](DEPLOYMENT.md): add `HF_TOKEN`, `OPENAI_API_KEY`, `APP_PASSWORD` as GitHub secrets, then run the workflow manually on `langgraph-ui`.
3. Check the first real conversations through each agent, especially adviser answers against `LearningPath.xlsx`.
4. Add Tavily / VirusTotal keys and test search and crawl with scanning on.
5. Set `LANGSMITH_TRACING=false` in local `.env` unless a LangSmith key is set (otherwise every request logs auth warnings).
6. Open a PR `langgraph-ui` → `main`; merging it turns on automatic deploys.
7. Later: persistent checkpointer (Postgres), tests for `url_scanner`, an OpenAI-embeddings option to drop torch from the image.
