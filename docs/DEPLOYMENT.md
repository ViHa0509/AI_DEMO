# Deployment: GitHub Actions → Hugging Face Spaces

The app runs as a Docker container on a free **Hugging Face Space** (2 vCPU, 16 GB RAM, sleeps when idle). GitHub Actions tests every push, and on `main` it deploys automatically.

```
push / PR ──► Tests (pytest) ──► Docker build + smoke test ──► Deploy (main or manual run only)
                                                                 │
                                       creates/updates the Space, syncs secrets, uploads the app
                                                                 ▼
                                                 https://<user>-ai-learning-assistant.hf.space
```

No database is needed: the learning paths in `vectordb/data/LearningPath.xlsx` are embedded into an in-memory vector store, pre-built inside the Docker image. Set `PGVECTOR_CONN` only if you want to use an external PGVector database (e.g. Neon or Supabase) instead.

## One-time setup (about 10 minutes)

### 1. Create a Hugging Face token
1. Sign up at <https://huggingface.co/join>.
2. Go to **Settings → Access Tokens → Create new token**, type **Write**, and copy it.

The Space is created automatically on the first deployment. You don't need to create it by hand.

### 2. Add GitHub secrets and variables
In the GitHub repo: **Settings → Secrets and variables → Actions**.

**Secrets** (tab "Secrets"):

| Name | Required | Value |
|---|---|---|
| `HF_TOKEN` | ✅ | The Hugging Face write token |
| `OPENAI_API_KEY` | ✅ | Your OpenAI key (stored in the Space as `API_KEY`) |
| `APP_PASSWORD` | ✅ | Password people type to use the app (protects your OpenAI quota) |
| `APP_SECRET` | optional | Any long random string; keeps users logged in across restarts |
| `TAVILY_API_KEY` | optional | Enables the web search agent |
| `VIRUSTOTAL_API_KEY` | optional | Scans URLs before crawling |
| `PGVECTOR_CONN` | optional | External PGVector database instead of the in-memory store |

**Variables** (tab "Variables"):

| Name | Default | Notes |
|---|---|---|
| `HF_SPACE` | `<hf-user>/ai-learning-assistant` | Space to deploy to |
| `AI_MODEL_PATH` | `gpt-4o-mini` | Any OpenAI chat model name |
| `AI_MODEL_API` | empty (= OpenAI) | Set only for another OpenAI-compatible provider |
| `RATE_LIMIT_PER_MINUTE` | `20` | Chat requests per client per minute |
| `SPACE_PRIVATE` | `false` | `true` = only you (logged in to HF) can open the Space |

> Deployment refuses to run without `APP_PASSWORD` unless `SPACE_PRIVATE=true` or `ALLOW_PUBLIC=true`.

### 3. Deploy
- **Automatic:** merge or push to `main`.
- **Manual:** GitHub → **Actions → CI/CD → Run workflow**, then pick a branch (handy to deploy `langgraph-ui` before merging).

The job summary prints the Space and app URLs. The first Hugging Face build takes about 5 to 10 minutes (torch + embedding model); later builds reuse cached layers.

## Day-to-day

| Task | How |
|---|---|
| Change a key or the password | Update the GitHub secret and re-run the workflow, or edit it directly in Space **Settings → Variables and secrets** |
| See logs | Space page → **Logs** (build and container logs) |
| Roll back | Re-run the workflow for an older commit, or revert the commit on `main` |
| Stop paying attention to it | The Space sleeps after inactivity and wakes on the next visit (takes about 30 s) |
| Run the image locally | `docker build -t ai-assistant . && docker run -p 7860:7860 --env-file .env ai-assistant` |

## Limits to know
- **Memory resets** when the Space sleeps or restarts (conversation memory is in-process). The browser keeps its chat list; the server simply forgets earlier context.
- **Single instance:** the rate limit and memory live in one process. That's fine for a personal project, not for horizontal scaling.
- Free-tier limits and sleep timing are set by Hugging Face and can change; check their pricing page.

## Security checklist
- [ ] **Rotate the keys leaked in git history** (HuggingFace, Tavily, LangSmith). The GitHub repo is **public**, so anyone can read them.
- [ ] `APP_PASSWORD` set to a strong value.
- [ ] Set a monthly usage limit on the OpenAI account (Settings → Limits) as a last line of defence.
- [ ] Never commit `.env`. It is in `.gitignore`; use `.env.example` as the template.
