"""Build and query a hybrid code index: Chroma (semantic) + BM25 (keyword).

Chroma's default embedding function is a local ONNX MiniLM model, so embeddings
are computed on-device with no API key and no PyTorch dependency.
"""
from __future__ import annotations

import re
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi

from ..config import settings
from .chunker import Chunk, chunk_file

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    # Split identifiers on camelCase and snake_case so "validateToken" matches
    # queries for "validate" or "token".
    raw = _TOKEN_RE.findall(text)
    out: list[str] = []
    for tok in raw:
        parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tok).replace("_", " ").split()
        out.extend(p.lower() for p in parts)
    return out


class CodeIndex:
    """Holds a per-repo Chroma collection plus an in-memory BM25 index."""

    def __init__(self, repo_name: str):
        self.repo_name = repo_name
        self._client = chromadb.PersistentClient(path=str(settings.chroma_path))
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", repo_name)[:60] or "repo"
        self.collection_name = f"code-{safe}"
        self._chunks: list[Chunk] = []
        self._bm25: BM25Okapi | None = None
        self._collection = None

    # ---- build ----
    def build(self, root: Path, files: list[tuple[str, str]]) -> int:
        """Index the given [(rel_path, language)] files. Returns chunk count."""
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = self._client.create_collection(
            name=self.collection_name, metadata={"hnsw:space": "cosine"}
        )

        all_chunks: list[Chunk] = []
        for rel, lang in files:
            all_chunks.extend(chunk_file(root, rel, lang))

        self._chunks = all_chunks
        if not all_chunks:
            return 0

        # Add to Chroma in batches (embedding happens here).
        batch = 256
        for i in range(0, len(all_chunks), batch):
            part = all_chunks[i:i + batch]
            self._collection.add(
                ids=[c.id for c in part],
                documents=[c.text for c in part],
                metadatas=[
                    {
                        "path": c.path,
                        "language": c.language,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                    }
                    for c in part
                ],
            )

        self._bm25 = BM25Okapi([_tokenize(c.text) for c in all_chunks])
        return len(all_chunks)

    # ---- load existing ----
    def load(self) -> bool:
        try:
            self._collection = self._client.get_collection(self.collection_name)
        except Exception:
            return False
        data = self._collection.get(include=["documents", "metadatas"])
        ids = data.get("ids", [])
        docs = data.get("documents", [])
        metas = data.get("metadatas", [])
        self._chunks = [
            Chunk(
                id=i,
                path=m.get("path", ""),
                language=m.get("language", ""),
                start_line=int(m.get("start_line", 1)),
                end_line=int(m.get("end_line", 1)),
                text=d,
            )
            for i, d, m in zip(ids, docs, metas)
        ]
        if self._chunks:
            self._bm25 = BM25Okapi([_tokenize(c.text) for c in self._chunks])
        return bool(self._chunks)

    # ---- query ----
    def search(self, query: str, k: int = 6) -> list[dict]:
        """Hybrid search: fuse semantic + keyword ranks (reciprocal rank fusion)."""
        if not self._chunks or self._collection is None:
            return []

        by_id = {c.id: c for c in self._chunks}
        scores: dict[str, float] = {}

        # Semantic ranking from Chroma.
        try:
            res = self._collection.query(
                query_texts=[query], n_results=min(k * 3, len(self._chunks))
            )
            sem_ids = res.get("ids", [[]])[0]
            for rank, cid in enumerate(sem_ids):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (rank + 60)
        except Exception:
            pass

        # Keyword ranking from BM25.
        if self._bm25 is not None:
            toks = _tokenize(query)
            if toks:
                bm = self._bm25.get_scores(toks)
                ranked = sorted(
                    range(len(bm)), key=lambda i: bm[i], reverse=True
                )[: k * 3]
                for rank, i in enumerate(ranked):
                    cid = self._chunks[i].id
                    scores[cid] = scores.get(cid, 0.0) + 1.0 / (rank + 60)

        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
        out: list[dict] = []
        for cid, score in top:
            c = by_id.get(cid)
            if not c:
                continue
            out.append(
                {
                    "path": c.path,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "language": c.language,
                    "score": round(score, 4),
                    "text": c.text,
                }
            )
        return out
