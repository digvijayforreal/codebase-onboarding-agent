"""Clone or open a git repository and enumerate its source files."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pathspec
from git import Repo

from ..config import settings

# Map file extensions to a human language name. Drives both filtering and
# the language breakdown shown in the UI.
EXT_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".scala": "Scala",
    ".m": "Objective-C",
    ".sh": "Shell",
}

# Directories we never want to treat as source.
IGNORE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__",
    "dist", "build", "target", ".next", ".nuxt", "vendor", ".idea",
    ".vscode", "coverage", ".pytest_cache", ".mypy_cache", "site-packages",
    "bin", "obj", ".cache", "migrations",
}

MAX_FILE_BYTES = 1_000_000  # skip very large/generated files


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-").lower() or "repo"


def is_remote(source: str) -> bool:
    return source.startswith(("http://", "https://", "git@")) or source.endswith(".git")


def resolve_repo(source: str) -> tuple[Repo, Path, str]:
    """Return (Repo, local_path, display_name) for a local path or remote URL.

    Remote URLs are cloned (shallow-ish but with full history for analysis)
    into the cache directory and reused on subsequent runs.
    """
    if is_remote(source):
        name = _slugify(source.rstrip("/").split("/")[-1].removesuffix(".git"))
        dest = settings.repos_path / name
        if dest.exists() and (dest / ".git").exists():
            repo = Repo(dest)
            try:
                repo.remotes.origin.fetch(prune=True)
            except Exception:
                pass  # offline is fine, we analyse what we have
        else:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            repo = Repo.clone_from(source, dest)
        return repo, dest, name

    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    repo = Repo(path)
    return repo, path, path.name


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    gi = root / ".gitignore"
    if not gi.exists():
        return None
    try:
        lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
        return pathspec.PathSpec.from_lines("gitwildmatch", lines)
    except Exception:
        return None


def list_source_files(root: Path) -> list[tuple[str, str]]:
    """Walk the repo and return [(relative_posix_path, language), ...].

    Honours .gitignore, skips known build/vendor dirs, binary and huge files.
    """
    spec = _load_gitignore(root)
    results: list[tuple[str, str]] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        rel_parts = path.relative_to(root).parts
        if any(part in IGNORE_DIRS for part in rel_parts):
            continue

        lang = EXT_LANGUAGE.get(path.suffix.lower())
        if lang is None:
            continue

        rel = path.relative_to(root).as_posix()
        if spec is not None and spec.match_file(rel):
            continue

        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue

        results.append((rel, lang))

    return results
