import socket

import pytest

from app import crawler


def test_find_url_strips_trailing_punctuation():
    assert crawler.find_url("read https://example.com/a?b=1.") == "https://example.com/a?b=1"
    assert crawler.find_url("no link here") is None


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"])
def test_private_addresses_are_blocked(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, (address, 0))])
    with pytest.raises(crawler.CrawlError):
        crawler.ensure_public_url("http://internal.example")


def test_public_address_is_allowed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.215.14", 0))])
    crawler.ensure_public_url("https://example.com")


def test_generic_extraction():
    html = """<html><head><title>My Page</title><meta name="description" content="Short intro.">
              <meta name="keywords" content="ai, python"></head>
              <body><nav>menu</nav><article><h1>Heading</h1><p>Body text.</p></article></body></html>"""
    [article] = crawler.extract_articles(html, "https://example.com")
    assert article["title"] == "My Page"
    assert article["tags_en"] == ["ai", "python"]
    assert "Body text." in article["summary_en"] and "menu" not in article["summary_en"]
