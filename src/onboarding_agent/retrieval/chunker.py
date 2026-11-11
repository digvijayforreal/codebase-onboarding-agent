"""Split source files into overlapping line-window chunks for indexing.

A function-aware splitter would be nicer, but a sliding window over lines is
language-agnostic and completely robust -- it never fails to parse. Each chunk
keeps its file path and line range so the agent can cite exact locations.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CHUNK_LINES = 60
OVERLAP_LINES = 12
MAX_CHUNKS_PER_FILE = 40


@dataclass
class Chunk:
    id: str
    path: str
    language: str
    start_line: int
    end_line: int
    text: str


def chunk_file(root: Path, rel_path: str, language: str) -> list[Chunk]:
    full = root / rel_path
    try:
        lines = full.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    if not lines:
        return []

    chunks: list[Chunk] = []
    step = max(1, CHUNK_LINES - OVERLAP_LINES)
    idx = 0
    for start in range(0, len(lines), step):
        window = lines[start:start + CHUNK_LINES]
        if not any(ln.strip() for ln in window):
            continue
        end = start + len(window)
        chunks.append(
            Chunk(
                id=f"{rel_path}:{start + 1}-{end}",
                path=rel_path,
                language=language,
                start_line=start + 1,
                end_line=end,
                text="\n".join(window),
            )
        )
        idx += 1
        if idx >= MAX_CHUNKS_PER_FILE:
            break
    return chunks
