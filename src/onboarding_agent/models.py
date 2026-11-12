"""Shared data models used across ingestion, analysis and the web layer."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class GitFileStats:
    """Per-file signals extracted from git history."""

    path: str
    commits: int = 0              # how many commits touched this file
    authors: int = 0             # distinct authors
    bugfix_commits: int = 0      # commits whose message looks like a fix
    churn: int = 0               # total lines added + deleted over history
    last_changed_days: float = 0.0   # days since last change (smaller = hotter)
    # recent activity buckets (newest-last), used by the forecaster
    monthly_commits: list[int] = field(default_factory=list)


@dataclass
class ComplexityStats:
    """Per-file static complexity from lizard."""

    path: str
    nloc: int = 0                # lines of code (no comments/blanks)
    avg_ccn: float = 0.0         # average cyclomatic complexity per function
    max_ccn: int = 0             # worst function complexity
    functions: int = 0
    token_count: int = 0


@dataclass
class FileReport:
    """Everything we know about one file, plus derived scores."""

    path: str
    language: str = ""
    nloc: int = 0
    avg_ccn: float = 0.0
    max_ccn: int = 0
    functions: int = 0
    commits: int = 0
    authors: int = 0
    bugfix_commits: int = 0
    churn: int = 0
    last_changed_days: float = 0.0

    # derived, 0..100
    complexity_score: float = 0.0
    instability_score: float = 0.0
    difficulty_score: float = 0.0
    hotspot_forecast: float = 0.0   # predicted near-future churn pressure, 0..100
    centrality: float = 0.0         # fan-in importance, 0..100

    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RepoReport:
    """Full analysis result for a repository."""

    name: str
    source: str
    total_files: int
    total_commits: int
    languages: dict[str, int]
    files: list[FileReport]
    generated_at: str
    graph: dict[str, Any] = field(default_factory=dict)  # file-level data-flow graph

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "total_files": self.total_files,
            "total_commits": self.total_commits,
            "languages": self.languages,
            "generated_at": self.generated_at,
            "files": [f.to_dict() for f in self.files],
            "graph": self.graph,
        }
