"""Extract per-file signals from git history: churn, authors, bug-fix density.

Uses a single `git log --numstat` call and parses it, which is orders of
magnitude faster than GitPython's per-commit `commit.stats` (that diffs every
commit individually and is unusable on repos with thousands of commits).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone

from git import Repo

from ..models import GitFileStats

# Commit messages that indicate a corrective change.
BUGFIX_RE = re.compile(
    r"\b(fix|fixes|fixed|bug|bugfix|hotfix|patch|revert|regression|crash|"
    r"issue|defect|broken|error|fault)\b",
    re.IGNORECASE,
)

RECENT_MONTHS = 12
MAX_COMMITS = 4000  # safety cap for very large histories

# Unit separator used to split commit header fields safely.
US = "\x1f"
HEADER = f"__C__{US}%H{US}%at{US}%ae{US}%s"


def _month_index(ts: int, now: datetime) -> int:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return (now.year - dt.year) * 12 + (now.month - dt.month)


def collect_git_stats(
    repo: Repo, tracked: set[str]
) -> tuple[dict[str, GitFileStats], int]:
    """Return (per-file stats, total_commit_count).

    `tracked` is the set of relative posix paths we care about (source files).
    """
    now = datetime.now(timezone.utc)
    stats: dict[str, GitFileStats] = {p: GitFileStats(path=p) for p in tracked}
    authors: dict[str, set[str]] = defaultdict(set)
    last_ts: dict[str, int] = {}
    monthly: dict[str, list[int]] = {p: [0] * RECENT_MONTHS for p in tracked}

    try:
        raw = repo.git.log(
            f"--max-count={MAX_COMMITS}",
            "--no-merges",
            "--numstat",
            f"--pretty=format:{HEADER}",
        )
    except Exception:
        return stats, 0

    total_commits = 0
    cur_ts = 0
    cur_bugfix = False
    cur_author = "unknown"

    for line in raw.splitlines():
        if line.startswith("__C__"):
            total_commits += 1
            parts = line.split(US)
            # parts = ["__C__", sha, at, email, subject]
            try:
                cur_ts = int(parts[2])
            except (IndexError, ValueError):
                cur_ts = 0
            cur_author = (parts[3] if len(parts) > 3 else "unknown").lower()
            subject = parts[4] if len(parts) > 4 else ""
            cur_bugfix = bool(BUGFIX_RE.search(subject))
            continue

        if not line.strip():
            continue

        # numstat line: added<TAB>deleted<TAB>path
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        added_s, deleted_s, raw_path = cols[0], cols[1], cols[2]

        # handle renames: "old => new" or "dir/{old => new}/file"
        path = _normalize_rename(raw_path)
        if path not in stats:
            continue

        added = 0 if added_s == "-" else int(added_s or 0)
        deleted = 0 if deleted_s == "-" else int(deleted_s or 0)

        s = stats[path]
        s.commits += 1
        s.churn += added + deleted
        if cur_bugfix:
            s.bugfix_commits += 1
        authors[path].add(cur_author)
        if cur_ts > last_ts.get(path, 0):
            last_ts[path] = cur_ts
        midx = _month_index(cur_ts, now)
        if 0 <= midx < RECENT_MONTHS:
            monthly[path][midx] += 1

    for path, s in stats.items():
        s.authors = len(authors[path])
        s.monthly_commits = list(reversed(monthly[path]))  # oldest-first
        if path in last_ts:
            s.last_changed_days = max(
                0.0, (now.timestamp() - last_ts[path]) / 86400.0
            )
        else:
            s.last_changed_days = 9999.0

    return stats, total_commits


def _normalize_rename(raw_path: str) -> str:
    """Resolve git's rename notation to the new path."""
    if "=>" not in raw_path:
        return raw_path.strip()
    # Form: prefix{old => new}suffix  OR  old => new
    m = re.match(r"^(.*)\{(.*) => (.*)\}(.*)$", raw_path)
    if m:
        prefix, _old, new, suffix = m.groups()
        return (prefix + new + suffix).replace("//", "/").strip()
    return raw_path.split("=>")[-1].strip()
