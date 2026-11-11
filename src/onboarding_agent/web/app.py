"""FastAPI application exposing analysis, tour and chat endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import settings
from ..service import session

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Codebase Onboarding Agent", version="0.1.0")


class AnalyzeRequest(BaseModel):
    source: str


class AskRequest(BaseModel):
    question: str


@app.get("/api/status")
def status():
    r = session.report
    return {
        "status": session.status,
        "message": session.message,
        "has_groq": settings.has_groq,
        "has_tavily": settings.has_tavily,
        "repo": r.name if r else None,
    }


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    source = req.source.strip()
    if not source:
        raise HTTPException(status_code=400, detail="source is required")
    try:
        report = session.analyze(source)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return report.to_dict()


@app.get("/api/report")
def report():
    if not session.report:
        raise HTTPException(status_code=404, detail="no analysis yet")
    return session.report.to_dict()


@app.post("/api/tour")
def tour():
    if not session.report:
        raise HTTPException(status_code=404, detail="no analysis yet")
    return session.tour()


@app.post("/api/ask")
def ask(req: AskRequest):
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required")
    return {"answer": session.ask(q)}


# ---- static frontend ----
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    html = STATIC_DIR / "index.html"
    if html.exists():
        return FileResponse(html)
    raise HTTPException(status_code=404, detail="frontend not built")
