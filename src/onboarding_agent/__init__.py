"""Codebase Onboarding Agent.

Point it at any git repository and it will:
  1. Ingest the file tree and full git history.
  2. Score each module's difficulty from code complexity + churn + bug-fix history.
  3. Forecast which modules are "heating up" (trending toward trouble).
  4. Index code with hybrid search (local embeddings + BM25).
  5. Use a Groq LLM agent (with Tavily web search) to build a guided tour
     and answer code-aware questions grounded in the real code.
"""

__version__ = "0.1.0"
