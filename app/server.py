"""FastAPI backend for the web UI.

Run:  python -m app.server        (or: uvicorn app.server:app --reload)
Open: http://localhost:8000
"""
import json
import logging
import os
import uuid
from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel, Field

from app.config import ROOT_DIR, settings
from app.graph import AGENT_NODES, graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Learning Assistant", version="1.0.0")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    thread_id: str = Field(default_factory=lambda: uuid.uuid4().hex, max_length=100)


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
        "features": {
            "adviser": bool(settings.pgvector_conn),
            "search": bool(settings.tavily_api_key),
            "crawl": True,
            "url_scan": bool(settings.virustotal_api_key),
        },
    }


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _chat_events(request),
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

    uvicorn.run("app.server:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
