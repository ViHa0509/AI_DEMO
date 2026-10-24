import json

import pytest
from fastapi.testclient import TestClient

from app import server
from app.security import AuthManager, RateLimiter


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "auth", AuthManager(None))
    monkeypatch.setattr(server, "chat_limiter", RateLimiter(0))
    return TestClient(server.app)  # not used as a context manager: skips the model warm-up


def _events(response) -> list[tuple[str, dict]]:
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["auth_required"] is False
    assert body["knowledge_backend"] == "in-memory"


def test_static_ui_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Learning Assistant" in response.text


def test_chat_streams_route_tokens_and_final(client, fake_llm):
    fake_llm("conversation", "Hello world")
    response = client.post("/api/chat", json={"message": "hi", "thread_id": "s1"})
    events = _events(response)
    names = [name for name, _ in events]

    assert names[0] == "route" and events[0][1] == {"route": "conversation"}
    assert names[-2:] == ["final", "done"]
    assert "".join(data["text"] for name, data in events if name == "token") == "Hello world"
    assert events[-2][1]["content"] == "Hello world"

    history = client.get("/api/threads/s1/messages").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]
    client.delete("/api/threads/s1")
    assert client.get("/api/threads/s1/messages").json()["messages"] == []


def test_chat_rejects_empty_message(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422


def test_password_protection(client, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthManager("secret-pw", secret="k"))
    monkeypatch.setattr(server, "login_limiter", RateLimiter(0))

    assert client.get("/api/health").json()["auth_required"] is True
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401
    assert client.post("/api/login", json={"password": "wrong"}).status_code == 401

    token = client.post("/api/login", json={"password": "secret-pw"}).json()["token"]
    response = client.get("/api/threads/x/messages", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_chat_rate_limit(client, monkeypatch, fake_llm):
    monkeypatch.setattr(server, "chat_limiter", RateLimiter(1))
    fake_llm("conversation", "ok")
    assert client.post("/api/chat", json={"message": "one"}).status_code == 200
    assert client.post("/api/chat", json={"message": "two"}).status_code == 429
