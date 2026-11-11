"""Cheap, language-agnostic 'centrality' = how many other files reference a file.

We approximate import/dependency fan-in by counting how often a file's module
name (its stem, e.g. `router` for `api/router.py`) appears in import/require/
include statements across the rest of the codebase. It is a heuristic, but it
reliably surfaces the 'spine' modules everything leans on.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

# Lines that look like dependency references in common languages.
IMPORTish = re.compile(
    r"^\s*(import|from|require|include|use|using)\b|require\(|import\(",
    re.IGNORECASE,
)


def compute_centrality(root: Path, rel_paths: list[str]) -> dict[str, float]:
    """Return {rel_path: raw_fan_in_count}."""
    stems: dict[str, str] = {}
    for rp in rel_paths:
        stem = Path(rp).stem
        if stem and stem not in ("__init__", "index", "mod"):
            stems.setdefault(stem, rp)

    # Build one regex that matches any known module stem as a whole word.
    if not stems:
        return {rp: 0.0 for rp in rel_paths}
    stem_re = re.compile(
        r"\b(" + "|".join(re.escape(s) for s in stems) + r")\b"
    )

    fan_in: Counter[str] = Counter()
    for rp in rel_paths:
        try:
            text = (root / rp).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        own_stem = Path(rp).stem
        for line in text.splitlines():
            if not IMPORTish.search(line):
                continue
            for match in stem_re.findall(line):
                if match == own_stem:
                    continue  # don't count self-references
                target = stems.get(match)
                if target and target != rp:
                    fan_in[target] += 1

    return {rp: float(fan_in.get(rp, 0)) for rp in rel_paths}
