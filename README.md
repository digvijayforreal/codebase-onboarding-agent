# Codebase Onboarding Agent

Point it at **any git repository** and it will:

1. **Ingest** the file tree and full git history.
2. **Score difficulty** per module from code complexity + churn + bug-fix history + fan-in centrality.
3. **Forecast hotspots** — which modules are "heating up" from their monthly commit trend.
4. **Index code** for hybrid search (local ONNX embeddings + BM25 keyword).
5. **Teach you the codebase** — a Groq LLM agent (with Tavily web search for third-party libs) builds a guided tour, easiest-first, and answers code-aware questions with file:line citations.

It turns a wall of unfamiliar code into a ranked map, a guided tour, and a code-aware assistant — the thing you wish a senior teammate gave you on day one.

## Tech stack

| Layer | Tool |
|-------|------|
| Git history | GitPython |
| Complexity | lizard (multi-language cyclomatic complexity) |
| Forecasting | recency-weighted trend over monthly commits (numpy) |
| Embeddings | ChromaDB built-in ONNX MiniLM (local, no key) |
| Keyword search | rank-bm25 |
| Hybrid fusion | reciprocal rank fusion of vector + BM25 |
| LLM agent | Groq (`llama-3.3-70b-versatile`) with tool calling |
| Web docs | Tavily |
| API + UI | FastAPI + animated vanilla-JS single page |
| Interop | MCP server (`mcp`) |

## Quickstart

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) and git on PATH. uv manages the Python version and every dependency for you.

```bash
uv sync          # create the venv + install everything from the lockfile
uv run onboard   # start the web app at http://127.0.0.1:8000
```

That's the whole setup. Open the URL, paste a GitHub URL (e.g. `https://github.com/pallets/flask`)
or a local path, and hit Analyze.

### API keys (optional)

On first run a `.env` is created for you. Add your keys to enable the LLM features:

```ini
GROQ_API_KEY=...     # enables the "Ask AI" chat + LLM-authored tour
TAVILY_API_KEY=...   # enables web search for third-party library docs
```

Everything else — the difficulty map, hotspots, hybrid search, data-flow view and a
deterministic fallback tour — works offline with no keys.

> Security: never commit `.env`. If a key was ever shared in plain text, rotate it.

### Other commands

```bash
uv run onboard serve --port 8080                                 # choose a port
uv run onboard analyze https://github.com/psf/requests --top 20  # terminal-only difficulty map
```

## Run as an MCP server

```bash
uv run python -m onboarding_agent.mcp_server
```

Then register the command in your MCP client (Kiro, Claude Desktop, Cursor). Tools:
`analyze_repo`, `get_difficulty_map`, `search_code`, `build_tour`, `ask`.

## How the scoring works (honest version)

- **complexity_score** — size (NLOC) + average & worst cyclomatic complexity.
- **instability_score** — commit count, churn, distinct authors, bug-fix ratio.
- **hotspot_forecast** — near-future churn pressure from the monthly commit trend.
- **centrality** — how many other files import/reference this one (the "spine").
- **difficulty_score** — weighted blend (0.40 complexity, 0.35 instability, 0.25 hotspot).

The difficulty score is a transparent **heuristic to guide attention**, not a validated
prediction of one person's experience. Weights live in `analysis/difficulty.py` and are
meant to be tuned against real newcomer feedback over time.

## Project layout

```
src/onboarding_agent/
  ingest/       repo_loader.py, git_history.py
  analysis/     complexity.py, forecast.py, centrality.py, difficulty.py
  retrieval/    chunker.py, index.py (Chroma + BM25 hybrid)
  agent/        groq_client.py, web_search.py (Tavily), tools.py, orchestrator.py
  web/          app.py (FastAPI) + static/ (funky UI)
  pipeline.py   source + git -> scored RepoReport
  service.py    in-memory session shared by web + MCP
  mcp_server.py MCP tool surface
  cli.py        `onboard serve` / `onboard analyze`
```
