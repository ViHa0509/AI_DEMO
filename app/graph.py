"""LangGraph workflow: classify the user message, then route it to one specialised agent.

    START -> classifier -> { adviser | conversation | search | crawl } -> END
"""
import json
import logging
import re
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langsmith import traceable
from typing_extensions import TypedDict

from app import crawler
from app.config import settings
from app.llm import get_llm
from app.prompts import get_prompt
from app.retriever import lookup_learning_paths
from app.url_scanner import VirusTotalChecker

logger = logging.getLogger(__name__)

Route = Literal["adviser", "conversation", "search", "crawl"]
ROUTES: tuple[Route, ...] = ("adviser", "conversation", "search", "crawl")
MAX_HISTORY = 20


class Source(TypedDict):
    title: str
    url: str


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    message_type: Route | None
    sources: list[Source]


def _history(state: State) -> list[BaseMessage]:
    return state["messages"][-MAX_HISTORY:]


def _ask_llm(state: State, system_prompt: str, config: RunnableConfig) -> str:
    messages = [SystemMessage(content=system_prompt), *_history(state)]
    return get_llm().invoke(messages, config).content


def _reply(content: str, sources: list[Source] | None = None) -> dict:
    return {"messages": [AIMessage(content=content)], "sources": sources or []}


# --- Classifier ---------------------------------------------------------------------------------

def _keyword_route(text: str) -> Route:
    """Cheap fallback when the LLM answer is not one of the known routes."""
    lowered = text.lower()
    if crawler.find_url(text):
        return "crawl"
    if re.search(r"\b(latest|news|today|current|price|weather|tin tức|hôm nay|mới nhất|giá)\b", lowered):
        return "search"
    if re.search(r"\b(learn|course|skill|roadmap|career|tutorial|học|khóa học|kỹ năng|lộ trình)\b", lowered):
        return "adviser"
    return "conversation"


def classify_message(state: State, config: RunnableConfig) -> dict:
    user_message = state["messages"][-1].content
    route: Route | None = None
    try:
        prompt = get_prompt("classify_prompt", user_message=user_message)
        answer = get_llm().invoke([{"role": "user", "content": prompt}], config).content.strip().lower()
        route = next((r for r in ROUTES if r in answer), None)
    except Exception as e:
        logger.error("Classifier LLM call failed: %s", e)

    if route is None:
        route = _keyword_route(user_message)
        logger.info("Classifier fallback route: %s", route)
    elif route == "crawl" and not crawler.find_url(user_message):
        route = "conversation"  # nothing to crawl without a URL
    logger.info("Route: %s", route)
    return {"message_type": route, "sources": []}


def route_message(state: State) -> Route:
    return state.get("message_type") or "conversation"


# --- Agents -------------------------------------------------------------------------------------

@traceable(name="Adviser Agent")
def adviser_agent(state: State, config: RunnableConfig) -> dict:
    """Skill / career questions answered from the PGVector learning-path knowledge base."""
    try:
        context, records = lookup_learning_paths(state["messages"][-1].content)
        reply = _ask_llm(state, get_prompt("skill_prompt", data=context), config)
        sources = [
            {"title": r.get("skill") or r.get("competency_area") or "Course", "url": r["course_link"]}
            for r in records
            if str(r.get("course_link", "")).startswith("http")
        ]
        return _reply(reply, sources)
    except Exception as e:
        logger.error("adviser_agent failed: %s", e)
        return _reply("Sorry, I ran into an error while looking up learning paths. Please try again.")


@traceable(name="Conversation Agent")
def conversation_agent(state: State, config: RunnableConfig) -> dict:
    """General conversation and small talk."""
    try:
        return _reply(_ask_llm(state, get_prompt("small_talk_prompt"), config))
    except Exception as e:
        logger.error("conversation_agent failed: %s", e)
        return _reply("I'm having trouble responding right now. Please try again in a moment.")


@traceable(name="Search Agent")
def search_agent(state: State, config: RunnableConfig) -> dict:
    """Up-to-date questions answered from Tavily web search results."""
    if not settings.tavily_api_key:
        return _reply("Web search is not configured. Set `TAVILY_API_KEY` in `.env` to enable it.")
    try:
        from tavily import TavilyClient

        query = state["messages"][-1].content
        results = TavilyClient(api_key=settings.tavily_api_key).search(query, max_results=5).get("results", [])
        if not results:
            return _reply("I couldn't find any relevant search results for your query.")

        sources = [{"title": r.get("title") or r["url"], "url": r["url"]} for r in results]
        context = json.dumps(
            [{"title": r.get("title"), "url": r["url"], "content": r.get("content", "")[:800]} for r in results],
            ensure_ascii=False,
        )
        return _reply(_ask_llm(state, get_prompt("search_prompt", data=context), config), sources)
    except Exception as e:
        logger.error("search_agent failed: %s", e)
        return _reply("I'm sorry, I couldn't perform the search right now. Please try again later.")


@traceable(name="Crawl Agent")
def crawl_agent(state: State, config: RunnableConfig) -> dict:
    """Fetch the URL in the message (after a safety scan) and summarise its content."""
    url = crawler.find_url(state["messages"][-1].content)
    if not url:
        return _reply("Please include the full URL (starting with http:// or https://) you want me to read.")

    if settings.virustotal_api_key:
        scan = VirusTotalChecker(settings.virustotal_api_key, timeout=settings.http_timeout).scan(url)
        if not scan.safe:
            logger.warning("Unsafe or unverified URL %s: %s", url, scan.reason)
            return _reply(f"⚠️ I won't open this link. {scan.reason}")
    elif settings.require_url_scan:
        return _reply("URL scanning is required but `VIRUSTOTAL_API_KEY` is not configured.")

    try:
        articles = crawler.extract_articles(crawler.fetch_html(url), url)
        data = json.dumps(articles, ensure_ascii=False, indent=2)
        sources = [{"title": a["title"], "url": a["url"]} for a in articles]
        return _reply(_ask_llm(state, get_prompt("crawl_prompt", data=data), config), sources)
    except crawler.CrawlError as e:
        return _reply(str(e))
    except Exception as e:
        logger.error("crawl_agent failed: %s", e)
        return _reply("I'm having trouble reading that page right now. Please try again later.")


# --- Graph --------------------------------------------------------------------------------------

AGENT_NODES = {
    "adviser": adviser_agent,
    "conversation": conversation_agent,
    "search": search_agent,
    "crawl": crawl_agent,
}


def build_graph(checkpointer=None):
    builder = StateGraph(State)
    builder.add_node("classifier", classify_message)
    for name, node in AGENT_NODES.items():
        builder.add_node(name, node)
        builder.add_edge(name, END)

    builder.add_edge(START, "classifier")
    builder.add_conditional_edges("classifier", route_message, {name: name for name in AGENT_NODES})
    return builder.compile(checkpointer=checkpointer if checkpointer is not None else MemorySaver())


graph = build_graph()
