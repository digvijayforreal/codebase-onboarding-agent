"""Thin wrapper around the Groq chat completions API."""
from __future__ import annotations

from ..config import settings

_client = None


def get_client():
    global _client
    if _client is None:
        from groq import Groq

        _client = Groq(api_key=settings.groq_api_key)
    return _client


def chat(messages: list[dict], tools: list[dict] | None = None,
         temperature: float = 0.2, max_tokens: int = 700):
    """Call Groq chat completions. Returns the raw message object."""
    kwargs: dict = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = get_client().chat.completions.create(**kwargs)
    return resp.choices[0].message
