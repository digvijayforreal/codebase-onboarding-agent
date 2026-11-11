"""End-to-end analysis pipeline: source + git history -> scored RepoReport."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .analysis import centrality as centrality_mod
from .analysis import complexity as complexity_mod
from .analysis import difficulty as diff_mod
from .analysis.forecast import forecast_pressure
from .ingest.git_history import collect_git_stats
from .ingest.repo_loader import list_source_files, resolve_repo
from .models import FileReport, RepoReport


def analyze_repo(source: str, max_files: int = 1500) -> tuple[RepoReport, Path]:
    """Analyse a local path or remote git URL and return (report, local_root)."""
    repo, root, name = resolve_repo(source)

    files = list_source_files(root)
    if len(files) > max_files:
        files = files[:max_files]
    rel_paths = [rel for rel, _ in files]
    lang_by_path = dict(files)
    tracked = set(rel_paths)

    # --- gather raw signals ---
    git_stats, total_commits = collect_git_stats(repo, tracked)
    centrality_raw = centrality_mod.compute_centrality(root, rel_paths)

    complexities = {}
    for rel in rel_paths:
        complexities[rel] = complexity_mod.analyze_file(root, rel)

    # --- normalisation bounds ---
    max_nloc = max((c.nloc for c in complexities.values()), default=1) or 1
    max_churn = max((g.churn for g in git_stats.values()), default=1) or 1
    max_commits = max((g.commits for g in git_stats.values()), default=1) or 1
    pressures = {
        rel: forecast_pressure(git_stats[rel].monthly_commits) for rel in rel_paths
    }
    max_pressure = max(pressures.values(), default=1.0) or 1.0
    max_central = max(centrality_raw.values(), default=1.0) or 1.0

    # --- build per-file reports ---
    reports: list[FileReport] = []
    for rel in rel_paths:
        c = complexities[rel]
        g = git_stats[rel]

        comp_score = diff_mod.compute_complexity_score(
            c.nloc, c.avg_ccn, c.max_ccn, max_nloc
        )
        inst_score = diff_mod.compute_instability_score(
            g.commits, g.authors, g.bugfix_commits, g.churn, max_churn, max_commits
        )
        hot_score = diff_mod.compute_hotspot_score(pressures[rel], max_pressure)
        central = round(100.0 * (centrality_raw[rel] / max_central), 1)
        difficulty = diff_mod.compute_difficulty(comp_score, inst_score, hot_score)

        reasons = diff_mod.explain(
            comp_score, inst_score, hot_score,
            g.bugfix_commits, g.authors, c.max_ccn, central,
        )

        reports.append(
            FileReport(
                path=rel,
                language=lang_by_path.get(rel, ""),
                nloc=c.nloc,
                avg_ccn=round(c.avg_ccn, 2),
                max_ccn=c.max_ccn,
                functions=c.functions,
                commits=g.commits,
                authors=g.authors,
                bugfix_commits=g.bugfix_commits,
                churn=g.churn,
                last_changed_days=round(g.last_changed_days, 1),
                complexity_score=comp_score,
                instability_score=inst_score,
                hotspot_forecast=hot_score,
                centrality=central,
                difficulty_score=difficulty,
                reasons=reasons,
            )
        )

    reports.sort(key=lambda r: r.difficulty_score, reverse=True)

    languages = Counter(lang_by_path.values())

    report = RepoReport(
        name=name,
        source=source,
        total_files=len(rel_paths),
        total_commits=total_commits,
        languages=dict(languages),
        files=reports,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    return report, root
