"""Combine complexity, instability and forecast signals into difficulty scores.

Scores are all normalised to 0..100 so they are easy to render and compare.

Honesty note: `difficulty_score` is a transparent weighted heuristic, not a
validated prediction of a specific person's experience. It is an estimate meant
to *guide* attention. The weights live here so they can be tuned later against
real newcomer feedback.
"""
from __future__ import annotations

import math

# Relative weights for the final difficulty blend. Must sum to ~1.0.
W_COMPLEXITY = 0.40
W_INSTABILITY = 0.35
W_HOTSPOT = 0.25


def _norm(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _log(value: float) -> float:
    return math.log1p(max(0.0, value))


def compute_complexity_score(
    nloc: int, avg_ccn: float, max_ccn: int, max_nloc: float
) -> float:
    """0..100: how intrinsically hard the code is to read."""
    size = _norm(_log(nloc), 0.0, _log(max_nloc) or 1.0)
    avg = _norm(avg_ccn, 1.0, 15.0)
    worst = _norm(max_ccn, 1.0, 40.0)
    return round(100.0 * (0.35 * size + 0.35 * avg + 0.30 * worst), 1)


def compute_instability_score(
    commits: int, authors: int, bugfix_commits: int,
    churn: int, max_churn: float, max_commits: float,
) -> float:
    """0..100: how troublesome the file has been historically."""
    commit_n = _norm(_log(commits), 0.0, _log(max_commits) or 1.0)
    churn_n = _norm(_log(churn), 0.0, _log(max_churn) or 1.0)
    authors_n = _norm(authors, 1.0, 8.0)
    bug_ratio = (bugfix_commits / commits) if commits else 0.0
    return round(
        100.0 * (0.30 * commit_n + 0.25 * churn_n + 0.20 * authors_n + 0.25 * bug_ratio),
        1,
    )


def compute_hotspot_score(pressure: float, max_pressure: float) -> float:
    """0..100: predicted near-future churn pressure (is it heating up?)."""
    return round(100.0 * _norm(pressure, 0.0, max_pressure or 1.0), 1)


def compute_difficulty(
    complexity_score: float, instability_score: float, hotspot_score: float
) -> float:
    """0..100 final blend used to rank where a newcomer will struggle."""
    return round(
        W_COMPLEXITY * complexity_score
        + W_INSTABILITY * instability_score
        + W_HOTSPOT * hotspot_score,
        1,
    )


def explain(
    complexity_score: float, instability_score: float, hotspot_score: float,
    bugfix_commits: int, authors: int, max_ccn: int, centrality: float,
) -> list[str]:
    """Human-readable reasons for the score, shown in the UI and used by the agent."""
    reasons: list[str] = []
    if complexity_score >= 60:
        reasons.append(f"High code complexity (worst function CCN {max_ccn}).")
    if instability_score >= 60:
        reasons.append(
            f"Changes often and has had {bugfix_commits} bug-fix commits."
        )
    if authors >= 5:
        reasons.append(f"Touched by {authors} different authors (shared ownership).")
    if hotspot_score >= 60:
        reasons.append("Activity is accelerating - it is a current hotspot.")
    if centrality >= 60:
        reasons.append("Central module: many other files depend on it.")
    if not reasons:
        reasons.append("Relatively self-contained and stable.")
    return reasons
