"""FastAPI backend for the web UI.

Run:  python -m app.server        (or: uvicorn app.server:app --reload)
Open: http://localhost:8000
"""
import json
import logging
import threading
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel, Field

from app.config import ROOT_DIR, settings
from app.graph import AGENT_NODES, graph
from app.retriever import get_retriever, knowledge_backend
from app.security import AuthManager, RateLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PUBLIC_API_PATHS = {"/api/health", "/api/login"}

auth = AuthManager(settings.app_password, settings.app_secret)
chat_limiter = RateLimiter(settings.rate_limit_per_minute)
login_limiter = RateLimiter(10)  # slows down password guessing


def _warm_up_knowledge_base() -> None:
    try:
        get_retriever()
        logger.info("Knowledge base ready (%s)", knowledge_backend())
    except Exception as e:
        logger.warning("Knowledge base warm-up failed: %s", e)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load the embedding model in the background so the first adviser question is fast
    threading.Thread(target=_warm_up_knowledge_base, daemon=True).start()
    if not auth.enabled:
        logger.warning("APP_PASSWORD is not set: the chat API is open to anyone who can reach it")
    yield


app = FastAPI(title="AI Learning Assistant", version="1.1.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    thread_id: str = Field(default_factory=lambda: uuid.uuid4().hex, max_length=100)


class LoginRequest(BaseModel):
    password: str = Field(..., max_length=200)


def _client_key(request: Request) -> str:
    # Behind a reverse proxy (e.g. Hugging Face Spaces) the right-most X-Forwarded-For entry
    # is the address the proxy itself saw, so it cannot be spoofed by the client.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else None
        if not auth.verify_token(token):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return await call_next(request)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chat_events(request: ChatRequest) -> Iterator[str]:
    """Run the graph and stream: route -> token* -> final -> done (or error)."""
    config = {"configurable": {"thread_id": request.thread_id}}
    inputs = {"messages": [HumanMessage(content=request.message.strip())]}
    try:
        for mode, payload in graph.stream(inputs, config, stream_mode=["updates", "messages"]):
            if mode == "messages":
                chunk, metadata = payload
                if (
                    isinstance(chunk, AIMessageChunk)
                    and chunk.content
                    and metadata.get("langgraph_node") in AGENT_NODES
                ):
                    yield _sse("token", {"text": chunk.content})
                continue

            for node, update in (payload or {}).items():
                if node == "classifier":
                    yield _sse("route", {"route": update["message_type"]})
                elif node in AGENT_NODES:
                    reply = update["messages"][-1]
                    yield _sse("final", {"content": reply.content, "sources": update.get("sources", [])})
    except Exception as e:
        logger.exception("Chat stream failed")
        yield _sse("error", {"message": f"Server error: {e.__class__.__name__}"})
    yield _sse("done", {"thread_id": request.thread_id})


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": settings.model_name,
        "auth_required": auth.enabled,
        "knowledge_backend": knowledge_backend(),
        "features": {
            "adviser": True,
            "search": bool(settings.tavily_api_key),
            "crawl": True,
            "url_scan": bool(settings.virustotal_api_key),
        },
    }


@app.post("/api/login")
def login(body: LoginRequest, request: Request):
    if not auth.enabled:
        return {"token": None, "expires_in": None}
    if not login_limiter.allow(_client_key(request)):
        return JSONResponse({"detail": "Too many attempts, try again in a minute"}, status_code=429)
    if not auth.check_password(body.password):
        return JSONResponse({"detail": "Wrong password"}, status_code=401)
    return {"token": auth.issue_token(), "expires_in": auth.ttl_seconds}


@app.post("/api/chat")
def chat(body: ChatRequest, request: Request):
    if not chat_limiter.allow(_client_key(request)):
        return JSONResponse({"detail": "Rate limit reached, please wait a minute"}, status_code=429)
    return StreamingResponse(
        _chat_events(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/threads/{thread_id}/messages")
def thread_messages(thread_id: str) -> dict:
    """Conversation stored in the server-side graph memory (empty after a server restart)."""
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    messages = snapshot.values.get("messages", []) if snapshot else []
    return {
        "thread_id": thread_id,
        "messages": [
            {"role": "assistant" if isinstance(m, AIMessage) else "user", "content": m.content} for m in messages
        ],
    }


@app.delete("/api/threads/{thread_id}")
def delete_thread(thread_id: str) -> dict:
    graph.checkpointer.delete_thread(thread_id)
    return {"deleted": thread_id}


# The static UI is mounted last so it never shadows the /api routes
app.mount("/", StaticFiles(directory=ROOT_DIR / "web", html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.server:app", host=settings.host, port=settings.port)
