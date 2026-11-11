"""In-memory session: analyse a repo, build the index, hold the agent.

Keeps the most recent analysis so the web endpoints can share it. For a single
user / demo this is plenty; a multi-user deployment would key this by session.
"""
from __future__ import annotations

import threading
from pathlib import Path

from .agent.orchestrator import OnboardingAgent
from .models import RepoReport
from .pipeline import analyze_repo
from .retrieval.index import CodeIndex


class Session:
    def __init__(self):
        self._lock = threading.Lock()
        self.report: RepoReport | None = None
        self.index: CodeIndex | None = None
        self.agent: OnboardingAgent | None = None
        self.root: Path | None = None
        self.status: str = "idle"       # idle | analyzing | ready | error
        self.message: str = ""

    def analyze(self, source: str) -> RepoReport:
        with self._lock:
            self.status = "analyzing"
            self.message = f"Analyzing {source}"
        try:
            report, root = analyze_repo(source)
            index = CodeIndex(report.name)
            files = [(f.path, f.language) for f in report.files]
            n_chunks = index.build(root, files)

            agent = OnboardingAgent(report, index, root)
            with self._lock:
                self.report = report
                self.index = index
                self.agent = agent
                self.root = root
                self.status = "ready"
                self.message = (
                    f"Indexed {report.total_files} files, {n_chunks} chunks."
                )
            return report
        except Exception as exc:
            with self._lock:
                self.status = "error"
                self.message = str(exc)
            raise

    def ask(self, question: str) -> str:
        if not self.agent:
            return "No repository analysed yet. Analyse a repo first."
        return self.agent.ask(question)

    def tour(self) -> dict:
        if not self.agent:
            return {"summary": "No repository analysed yet.", "steps": []}
        return self.agent.build_tour()


session = Session()
