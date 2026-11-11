"""The agent: answers questions and builds guided tours, grounded in the repo."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import settings
from ..models import RepoReport
from ..retrieval.index import CodeIndex
from . import groq_client
from .tools import TOOL_SCHEMAS, ToolBox

MAX_TOOL_ROUNDS = 3

QA_SYSTEM = """You are a senior engineer onboarding a newcomer to an unfamiliar codebase.
Use search_code to find relevant code before answering. Cite files and line ranges like
`api/router.py:40-72`. Be concise and concrete. Use web_search only for external libraries."""

TOUR_SYSTEM = """You design an onboarding tour of a codebase for a new developer.
You are given the difficulty map (hardest modules). Design an ordered tour of 6-8 steps
that starts at simple, central entry points and moves toward the hardest modules, saving
the most difficult for last with a warning. You may call tools to inspect code first.
Respond with ONLY a JSON object (no markdown fences) of the form:
{
  "summary": "2-3 sentence orientation to the whole repo",
  "steps": [
    {
      "path": "relative/file/path",
      "title": "short title",
      "why": "why this matters / why now in the order",
      "difficulty": 0-100,
      "watch_out": "optional gotcha, or empty string"
    }
  ]
}"""


class OnboardingAgent:
    def __init__(self, report: RepoReport, index: CodeIndex, root: Path):
        self.report = report
        self.tools = ToolBox(report, index, root)

    # ---------- shared tool loop ----------
    def _run_loop(self, messages: list[dict], max_rounds: int = MAX_TOOL_ROUNDS):
        try:
            return self._loop(messages, max_rounds)
        except Exception as exc:
            return _friendly_error(exc)

    def _loop(self, messages: list[dict], max_rounds: int):
        # gpt-oss models can emit a tool call even when tools are omitted,
        # which Groq rejects with a 400. So we ALWAYS pass tools and instead
        # nudge the model to finalise on the last round.
        for i in range(max_rounds):
            last_round = i == max_rounds - 1
            if last_round:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Stop using tools now. Give your final answer in plain "
                            "text with file:line citations based on what you found."
                        ),
                    }
                )

            msg = groq_client.chat(messages, tools=TOOL_SCHEMAS)
            tool_calls = getattr(msg, "tool_calls", None)

            if not tool_calls:
                return msg.content or ""
            if last_round:
                # Still trying to call tools; return whatever text it gave, or a hint.
                return (
                    msg.content
                    or "I gathered context but need a more specific question to answer well."
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self.tools.dispatch(tc.function.name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": result,
                    }
                )
        return ""

    # ---------- public API ----------
    def ask(self, question: str) -> str:
        if not settings.has_groq:
            return _no_key_message()

        # RAG-first: pre-fetch the most relevant code and inject it so the model
        # can usually answer in a single call. It may still call tools for more.
        hits = self.tools.index.search(question, k=4)
        context = "\n\n".join(
            f"// {h['path']}:{h['start_line']}-{h['end_line']}\n{h['text'][:320]}"
            for h in hits
        ) or "(no snippets found)"

        user = (
            f"Question: {question}\n\n"
            f"Relevant code from hybrid search:\n{context}\n\n"
            "Answer concisely using these snippets, citing file:line. "
            "Only call a tool if the snippets are clearly insufficient."
        )
        messages = [
            {"role": "system", "content": QA_SYSTEM},
            {"role": "user", "content": user},
        ]
        return self._run_loop(messages)

    def build_tour(self) -> dict:
        if not settings.has_groq:
            return self._fallback_tour()
        difficulty_context = json.dumps(
            [
                {
                    "path": f.path,
                    "difficulty": f.difficulty_score,
                    "centrality": f.centrality,
                    "reasons": f.reasons[:2],
                }
                for f in self.report.files[:10]
            ]
        )
        messages = [
            {"role": "system", "content": TOUR_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Repository: {self.report.name}\n"
                    f"Languages: {self.report.languages}\n"
                    f"Difficulty map (hardest first):\n{difficulty_context}\n\n"
                    "Design the tour now."
                ),
            },
        ]
        raw = self._run_loop(messages)
        tour = _parse_json(raw)
        if tour and "steps" in tour:
            return tour
        return self._fallback_tour()

    # ---------- fallback when no LLM key ----------
    def _fallback_tour(self) -> dict:
        """Deterministic tour so the app is useful even without a Groq key."""
        files = self.report.files
        spine = sorted(files, key=lambda f: f.centrality, reverse=True)[:3]
        hard = files[:4]  # already sorted by difficulty desc
        seen: set[str] = set()
        steps = []
        for f in spine + hard:
            if f.path in seen:
                continue
            seen.add(f.path)
            steps.append(
                {
                    "path": f.path,
                    "title": Path(f.path).name,
                    "why": "; ".join(f.reasons),
                    "difficulty": f.difficulty_score,
                    "watch_out": (
                        "Hardest area - study last." if f.difficulty_score >= 60 else ""
                    ),
                }
            )
        return {
            "summary": (
                f"{self.report.name}: {self.report.total_files} files, "
                f"{self.report.total_commits} commits. Start at the central modules, "
                "then work toward the highest-difficulty ones."
            ),
            "steps": steps,
        }


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "rate_limit" in text or "413" in text or "429" in text or "too large" in text:
        return (
            "The Groq free tier hit its tokens-per-minute limit on this answer. "
            "Wait ~30 seconds and try a shorter question, or upgrade the Groq tier. "
            "The difficulty map, hotspots, hybrid search and fallback tour still work."
        )
    return f"The LLM call failed: {text}"


def _no_key_message() -> str:
    return (
        "No Groq API key is configured, so live Q&A is disabled. "
        "Add GROQ_API_KEY to your .env to enable the agent. "
        "The difficulty map, hotspots and guided tour still work without it."
    )


def _parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
