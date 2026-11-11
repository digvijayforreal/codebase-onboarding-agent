"""MCP server exposing the onboarding engine as tools for any MCP client.

Run with:  python -m onboarding_agent.mcp_server
Then point an MCP client (Kiro, Claude Desktop, Cursor) at this command.

Tools:
  analyze_repo(source)        -> summary + top difficult files
  get_difficulty_map(limit)   -> ranked difficulty list
  search_code(query)          -> hybrid code search hits
  build_tour()                -> guided onboarding tour
  ask(question)               -> code-aware answer from the agent
"""
from __future__ import annotations

import json

from .service import session

try:
    # mcp >= 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except Exception:
    try:
        # mcp 1.x
        from mcp.server.fastmcp import FastMCP as _Server
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "The 'mcp' package is required for the MCP server. Install deps first."
        ) from exc

mcp = _Server("codebase-onboarding")


@mcp.tool()
def analyze_repo(source: str) -> str:
    """Analyse a git repo (local path or URL). Returns a JSON summary."""
    report = session.analyze(source)
    return json.dumps(
        {
            "name": report.name,
            "files": report.total_files,
            "commits": report.total_commits,
            "languages": report.languages,
            "hardest": [
                {"path": f.path, "difficulty": f.difficulty_score, "reasons": f.reasons}
                for f in report.files[:10]
            ],
        }
    )


@mcp.tool()
def get_difficulty_map(limit: int = 15) -> str:
    """Return the ranked difficulty map of the analysed repo as JSON."""
    if not session.report:
        return json.dumps({"error": "analyze a repo first"})
    return json.dumps(
        [
            {
                "path": f.path,
                "difficulty": f.difficulty_score,
                "complexity": f.complexity_score,
                "instability": f.instability_score,
                "hotspot": f.hotspot_forecast,
                "centrality": f.centrality,
                "reasons": f.reasons,
            }
            for f in session.report.files[:limit]
        ]
    )


@mcp.tool()
def search_code(query: str) -> str:
    """Hybrid (semantic + keyword) search over the analysed repo's code."""
    if not session.index:
        return json.dumps({"error": "analyze a repo first"})
    return json.dumps(session.index.search(query, k=6))


@mcp.tool()
def build_tour() -> str:
    """Build a guided onboarding tour of the analysed repo."""
    return json.dumps(session.tour())


@mcp.tool()
def ask(question: str) -> str:
    """Ask a code-aware question about the analysed repo."""
    return session.ask(question)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
