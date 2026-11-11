"""Tavily web search: pull docs for unfamiliar third-party libraries."""
from __future__ import annotations

from ..config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        from tavily import TavilyClient

        _client = TavilyClient(api_key=settings.tavily_api_key)
    return _client


def web_search(query: str, max_results: int = 4) -> list[dict]:
    """Return [{title, url, content}] for a query, or [] if unavailable."""
    if not settings.has_tavily:
        return []
    try:
        res = _get_client().search(
            query=query, max_results=max_results, search_depth="basic"
        )
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content", "") or "")[:600],
            }
            for r in res.get("results", [])
        ]
    except Exception:
        return []
