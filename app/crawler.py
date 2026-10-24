"""Fetch a web page and extract article data for the crawl agent."""
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://[^\s'\"`<>]+")
USER_AGENT = "Mozilla/5.0 (compatible; AI-Learning-Assistant/1.0)"
MAX_ARTICLES = 5
MAX_TEXT_CHARS = 4000


class CrawlError(Exception):
    """Raised with a user-facing message when a page cannot be crawled."""


def find_url(text: str) -> str | None:
    match = URL_PATTERN.search(text)
    return match.group(0).rstrip(".,;:!?)") if match else None


def ensure_public_url(url: str) -> None:
    """Block requests to localhost / private networks (SSRF protection)."""
    host = urlparse(url).hostname
    if not host:
        raise CrawlError("The URL has no host name.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        raise CrawlError(f"Could not resolve host `{host}`.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise CrawlError("Crawling internal or private network addresses is not allowed.")


def fetch_html(url: str) -> str:
    ensure_public_url(url)
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=settings.http_timeout)
    except requests.RequestException as e:
        logger.error("Failed to fetch %s: %s", url, e)
        raise CrawlError("I couldn't reach that page. Please check the URL and try again.")
    if response.status_code != 200:
        raise CrawlError(f"The page returned HTTP {response.status_code}.")
    return response.text


def _meta(node, **attrs) -> str | None:
    tag = node.find("meta", attrs=attrs)
    return tag["content"].strip() if tag and tag.get("content") else None


def _extract_blogger_posts(soup: BeautifulSoup, url: str) -> list[dict]:
    """Structured extraction for Blogger-style news sites (e.g. thehackernews.com)."""
    articles = []
    for post in soup.select("div.blog-posts div.post")[:MAX_ARTICLES]:
        body = post.find("div", id="articlebody")
        paragraphs = body.find_all("p") if body else []
        author_block = post.find("div", itemprop="author")
        link = post.find("link", itemprop=re.compile("url"))
        tags = post.select("div.tags a[rel=tag]")
        post_url = link["href"] if link and link.get("href") else url
        articles.append({
            "id": post_url,
            "title": _meta(post, itemprop="headline") or "Title not found",
            "summary_en": " ".join(p.get_text(strip=True) for p in paragraphs[:3]),
            "tags_en": [t.get_text(strip=True) for t in tags],
            "by": (_meta(author_block, itemprop="name") if author_block else None) or "Unknown author",
            "url": post_url,
        })
    return articles


def _extract_generic(soup: BeautifulSoup, url: str) -> list[dict]:
    """Fallback for any page: title, description and main text."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    title = _meta(soup, property="og:title") or (soup.title.get_text(strip=True) if soup.title else url)
    description = _meta(soup, name="description") or _meta(soup, property="og:description") or ""
    container = soup.find("article") or soup.find("main") or soup.body or soup
    text = " ".join(p.get_text(" ", strip=True) for p in container.find_all(["h1", "h2", "h3", "p", "li"]))
    keywords = _meta(soup, name="keywords") or ""
    return [{
        "id": url,
        "title": title,
        "summary_en": (description + " " + text).strip()[:MAX_TEXT_CHARS],
        "tags_en": [k.strip() for k in keywords.split(",") if k.strip()],
        "by": _meta(soup, name="author") or "Unknown author",
        "url": url,
    }]


def extract_articles(html: str, url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    return _extract_blogger_posts(soup, url) or _extract_generic(soup, url)
