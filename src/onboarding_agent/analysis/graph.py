"""Build data-flow graphs for a repository.

Two levels:

* ``build_file_graph`` — a repo-wide dependency graph. Nodes are files, a
  directed edge ``A -> B`` means *A imports / references B* (so definitions and
  data flow from B into A). This reuses the same import-detection heuristic as
  :mod:`analysis.centrality`, but keeps the edges instead of only counting them.

* ``build_file_flow`` — for a single file, the functions it defines and the
  calls between them (how data moves *inside* the code), plus the files it
  depends on and the files that depend on it.

Both are deliberately lightweight, language-agnostic heuristics. They are meant
to give a newcomer a navigable mental model, not a compiler-grade call graph.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

import lizard

# Lines that look like dependency references in common languages.
IMPORTish = re.compile(
    r"^\s*(import|from|require|include|use|using)\b|require\(|import\(",
    re.IGNORECASE,
)

_SKIP_STEMS = {"__init__", "index", "mod"}

# cap so the animated flowchart stays legible and fast
MAX_NODES = 70


def _stem_map(rel_paths: list[str]) -> dict[str, str]:
    """Map a module stem (e.g. ``router``) to a representative file path."""
    stems: dict[str, str] = {}
    for rp in rel_paths:
        stem = Path(rp).stem
        if stem and stem not in _SKIP_STEMS:
            stems.setdefault(stem, rp)
    return stems


def _import_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if IMPORTish.search(ln)]


def build_file_graph(
    root: Path,
    rel_paths: list[str],
    lang_by_path: dict[str, str],
    difficulty_by_path: dict[str, float],
    centrality_by_path: dict[str, float],
) -> dict:
    """Return ``{"nodes": [...], "edges": [...]}`` for the whole repo."""
    stems = _stem_map(rel_paths)
    if not stems:
        return {"nodes": [], "edges": []}

    stem_re = re.compile(r"\b(" + "|".join(re.escape(s) for s in stems) + r")\b")

    edge_weight: Counter[tuple[str, str]] = Counter()
    for rp in rel_paths:
        try:
            text = (root / rp).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        own_stem = Path(rp).stem
        for line in _import_lines(text):
            for match in stem_re.findall(line):
                if match == own_stem:
                    continue
                target = stems.get(match)
                if target and target != rp:
                    edge_weight[(rp, target)] += 1

    # degree = in + out, used to pick the most connected nodes to display
    degree: Counter[str] = Counter()
    for (a, b), w in edge_weight.items():
        degree[a] += w
        degree[b] += w

    # rank nodes: prefer connected + central + hard files, keep the top slice
    def node_rank(rp: str) -> float:
        return (
            degree.get(rp, 0) * 2.0
            + centrality_by_path.get(rp, 0.0) / 10.0
            + difficulty_by_path.get(rp, 0.0) / 20.0
        )

    ranked = sorted(rel_paths, key=node_rank, reverse=True)
    kept = {rp for rp in ranked if degree.get(rp, 0) > 0}
    if len(kept) > MAX_NODES:
        kept = set(sorted(kept, key=node_rank, reverse=True)[:MAX_NODES])
    if not kept:
        return {"nodes": [], "edges": []}

    edges = [
        {"source": a, "target": b, "weight": w}
        for (a, b), w in edge_weight.items()
        if a in kept and b in kept
    ]

    layer = _assign_layers(kept, edges)

    nodes = []
    for rp in kept:
        nodes.append(
            {
                "id": rp,
                "label": Path(rp).name,
                "group": rp.split("/", 1)[0] if "/" in rp else "(root)",
                "language": lang_by_path.get(rp, ""),
                "difficulty": round(difficulty_by_path.get(rp, 0.0), 1),
                "centrality": round(centrality_by_path.get(rp, 0.0), 1),
                "layer": layer.get(rp, 0),
                "in_degree": sum(1 for e in edges if e["target"] == rp),
                "out_degree": sum(1 for e in edges if e["source"] == rp),
            }
        )
    nodes.sort(key=lambda n: (n["layer"], n["id"]))
    return {"nodes": nodes, "edges": edges}


def _assign_layers(kept: set[str], edges: list[dict]) -> dict[str, int]:
    """Longest-path depth from entry points (no incoming edge), cycle-safe."""
    out_adj: dict[str, list[str]] = defaultdict(list)
    indeg: Counter[str] = Counter()
    for e in edges:
        out_adj[e["source"]].append(e["target"])
        indeg[e["target"]] += 1

    layer: dict[str, int] = {}

    def depth(node: str, seen: frozenset[str]) -> int:
        if node in layer:
            return layer[node]
        if node in seen:  # cycle guard
            return 0
        children = out_adj.get(node, [])
        if not children:
            d = 0
        else:
            d = 1 + max(depth(c, seen | {node}) for c in children)
        layer[node] = d
        return d

    for n in kept:
        depth(n, frozenset())
    return layer


def build_file_flow(
    root: Path,
    rel_path: str,
    all_rel_paths: list[str],
    repo_edges: list[dict] | None = None,
) -> dict:
    """Internal function-call flow for one file, plus its file-level neighbours."""
    full = root / rel_path
    try:
        text = full.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""
    lines = text.splitlines()

    functions: list[dict] = []
    calls: list[dict] = []
    try:
        analysis = lizard.analyze_file(str(full))
        funcs = list(analysis.function_list)
    except Exception:
        funcs = []

    if funcs:
        name_to_id: dict[str, str] = {}
        for i, f in enumerate(funcs):
            fid = f"fn{i}"
            name_to_id[f.name] = fid
            functions.append(
                {
                    "id": fid,
                    "name": f.name,
                    "long_name": getattr(f, "long_name", f.name),
                    "ccn": f.cyclomatic_complexity,
                    "nloc": getattr(f, "nloc", 0),
                    "params": len(getattr(f, "parameters", []) or []),
                    "start_line": getattr(f, "start_line", 0),
                    "end_line": getattr(f, "end_line", 0),
                }
            )

        # intra-file call edges: scan each function body for other function names
        seen_edges: set[tuple[str, str]] = set()
        for f in funcs:
            start = max(0, getattr(f, "start_line", 1) - 1)
            end = min(len(lines), getattr(f, "end_line", start + 1))
            body = "\n".join(lines[start:end])
            for other in funcs:
                if other.name == f.name:
                    continue
                if re.search(r"\b" + re.escape(other.name) + r"\s*\(", body):
                    key = (name_to_id[f.name], name_to_id[other.name])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        calls.append({"source": key[0], "target": key[1]})

    # file-level neighbours from the import heuristic
    stems = _stem_map(all_rel_paths)
    stem_re = (
        re.compile(r"\b(" + "|".join(re.escape(s) for s in stems) + r")\b")
        if stems
        else None
    )
    own_stem = Path(rel_path).stem
    imports: list[str] = []
    if stem_re:
        seen_imp: set[str] = set()
        for line in _import_lines(text):
            for match in stem_re.findall(line):
                if match == own_stem:
                    continue
                target = stems.get(match)
                if target and target != rel_path and target not in seen_imp:
                    seen_imp.add(target)
                    imports.append(target)

    dependents: list[str] = []
    if repo_edges:
        dependents = sorted(
            {e["source"] for e in repo_edges if e["target"] == rel_path}
        )

    return {
        "path": rel_path,
        "functions": functions,
        "calls": calls,
        "imports": imports,
        "dependents": dependents,
    }
