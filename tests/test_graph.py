import uuid

import pytest

from app import graph as graph_module
from app.graph import _keyword_route, build_graph


@pytest.mark.parametrize(
    ("text", "route"),
    [
        ("summarize https://example.com please", "crawl"),
        ("latest news about AI", "search"),
        ("tin tức hôm nay", "search"),
        ("I want to learn Python", "adviser"),
        ("lộ trình học Java", "adviser"),
        ("hello there", "conversation"),
    ],
)
def test_keyword_route(text, route):
    assert _keyword_route(text) == route


def _run(graph, text):
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    return graph.invoke({"messages": [{"role": "user", "content": text}]}, config)


def test_routes_to_conversation(fake_llm):
    fake_llm("conversation", "Hi! How can I help?")
    state = _run(build_graph(), "hello")
    assert state["message_type"] == "conversation"
    assert state["messages"][-1].content == "Hi! How can I help?"


def test_unknown_classifier_output_uses_keyword_fallback(fake_llm):
    fake_llm("I am not sure", "Here is a learning plan.")
    state = _run(build_graph(), "I want to learn Python")
    assert state["message_type"] == "adviser"


def test_crawl_without_url_falls_back_to_conversation(fake_llm):
    fake_llm("crawl", "Sure.")
    state = _run(build_graph(), "crawl something for me")
    assert state["message_type"] == "conversation"


def test_search_without_key_explains_configuration(fake_llm):
    fake_llm("search")
    state = _run(build_graph(), "latest news")
    assert "TAVILY_API_KEY" in state["messages"][-1].content


def test_adviser_uses_knowledge_base_sources(fake_llm, monkeypatch):
    records = [{"skill": "Python - Beginner", "course_link": "https://learn.example/python"},
               {"skill": "No link", "course_link": "nan"}]
    monkeypatch.setattr(graph_module, "lookup_learning_paths", lambda q: ("[...]", records))
    fake_llm("adviser", "Start with Python basics.")
    state = _run(build_graph(), "how do I learn python")
    assert state["sources"] == [{"title": "Python - Beginner", "url": "https://learn.example/python"}]


def test_memory_keeps_history_per_thread(fake_llm):
    fake_llm("conversation", "one", "conversation", "two")
    graph = build_graph()
    config = {"configurable": {"thread_id": "t"}}
    graph.invoke({"messages": [{"role": "user", "content": "a"}]}, config)
    state = graph.invoke({"messages": [{"role": "user", "content": "b"}]}, config)
    assert [m.content for m in state["messages"]] == ["a", "one", "b", "two"]
