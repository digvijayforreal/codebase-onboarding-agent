"""Static code-complexity metrics via lizard (multi-language)."""
from __future__ import annotations

from pathlib import Path

import lizard

from ..models import ComplexityStats


def analyze_file(root: Path, rel_path: str) -> ComplexityStats:
    """Run lizard on one file and summarise its complexity.

    Falls back to a line count if lizard cannot parse the language.
    """
    full = root / rel_path
    try:
        analysis = lizard.analyze_file(str(full))
    except Exception:
        return _fallback(full, rel_path)

    funcs = list(analysis.function_list)
    if not funcs:
        # Non-code or unparsed file: still record NLOC so it is not invisible.
        return ComplexityStats(
            path=rel_path,
            nloc=getattr(analysis, "nloc", 0),
            functions=0,
            token_count=getattr(analysis, "token_count", 0),
        )

    ccns = [f.cyclomatic_complexity for f in funcs]
    return ComplexityStats(
        path=rel_path,
        nloc=analysis.nloc,
        avg_ccn=sum(ccns) / len(ccns),
        max_ccn=max(ccns),
        functions=len(funcs),
        token_count=analysis.token_count,
    )


def _fallback(full: Path, rel_path: str) -> ComplexityStats:
    try:
        text = full.read_text(encoding="utf-8", errors="ignore")
        nloc = sum(1 for ln in text.splitlines() if ln.strip())
    except Exception:
        nloc = 0
    return ComplexityStats(path=rel_path, nloc=nloc)
