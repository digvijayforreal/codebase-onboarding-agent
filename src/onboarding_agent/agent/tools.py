"""Tool implementations and their JSON schemas for the Groq agent."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import RepoReport
from ..retrieval.index import CodeIndex
from .web_search import web_search

# JSON schema advertised to the LLM for function/tool calling.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Hybrid semantic + keyword search over the repository's code. "
                "Use this to find where something is implemented. Returns code "
                "snippets with file paths and line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for."}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a slice of a source file by relative path and line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_difficulty_map",
            "description": (
                "Return the most difficult / highest-risk modules for a newcomer, "
                "with their scores and the reasons why."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "How many files."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for documentation about an unfamiliar third-party "
                "library or framework used in this repo. Use only for external tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


class ToolBox:
    """Binds tool calls to a specific repo, index and file root."""

    def __init__(self, report: RepoReport, index: CodeIndex, root: Path):
        self.report = report
        self.index = index
        self.root = root

    def dispatch(self, name: str, args: dict) -> str:
        try:
            if name == "search_code":
                return self._search_code(args.get("query", ""))
            if name == "read_file":
                return self._read_file(
                    args.get("path", ""),
                    args.get("start_line"),
                    args.get("end_line"),
                )
            if name == "get_difficulty_map":
                return self._difficulty_map(int(args.get("limit", 8)))
            if name == "web_search":
                return json.dumps(web_search(args.get("query", "")))
        except Exception as exc:  # never crash the loop on a bad tool call
            return json.dumps({"error": str(exc)})
        return json.dumps({"error": f"unknown tool {name}"})

    def _search_code(self, query: str) -> str:
        hits = self.index.search(query, k=4)
        slim = [
            {
                "path": h["path"],
                "lines": f"{h['start_line']}-{h['end_line']}",
                "snippet": h["text"][:360],
            }
            for h in hits
        ]
        return json.dumps(slim)

    def _read_file(self, path: str, start, end) -> str:
        full = self.root / path
        if not full.exists():
            return json.dumps({"error": f"no such file: {path}"})
        lines = full.read_text(encoding="utf-8", errors="ignore").splitlines()
        s = max(1, int(start)) if start else 1
        e = min(len(lines), int(end)) if end else min(len(lines), s + 120)
        body = "\n".join(lines[s - 1:e])
        return json.dumps({"path": path, "lines": f"{s}-{e}", "text": body[:1500]})

    def _difficulty_map(self, limit: int) -> str:
        top = self.report.files[:min(limit, 8)]
        return json.dumps(
            [
                {
                    "path": f.path,
                    "difficulty": f.difficulty_score,
                    "reasons": f.reasons[:2],
                }
                for f in top
            ]
        )
