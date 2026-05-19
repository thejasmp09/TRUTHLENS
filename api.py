"""
TruthLens FastAPI Backend
Run with: uvicorn api:app --reload
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
from typing import Optional
import config
from truthlens.db import init_db
from truthlens.pipeline import analyze_post_with_agents
from truthlens.report import generate_report_html

app = FastAPI(
    title="TruthLens API",
    description="Real-time misinformation autopsy agent",
    version="1.0.0"
)

# Allow React frontend to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  #CORS fix
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


# ── Models ──────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    content: str
    source_url: Optional[str] = "https://unknown.com"
    platform: Optional[str] = "manual"
    author: Optional[str] = "unknown"


# ── Routes ──────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "TruthLens API is running"}


@app.get("/reports")
def get_reports(limit: int = 20, offset: int = 0):
    """Get all reports for the dashboard."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT r.id, r.overall_verdict, r.confidence, r.created_at,
                  r.autopsy_md, r.claims_json, r.verdicts_json, r.agent_results_json,
                  p.platform, p.author, p.url, p.content
           FROM reports r
           JOIN posts p ON r.post_id = p.id
           ORDER BY r.created_at DESC
           LIMIT ? OFFSET ?""",
        (limit, offset)
    ).fetchall()

    total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    conn.close()

    reports = []
    for row in rows:
        r = dict(row)
        for key in ("claims_json", "verdicts_json", "agent_results_json"):
            if r.get(key):
                try:
                    r[key] = json.loads(r[key])
                except Exception:
                    pass
        reports.append(r)

    return {"reports": reports, "total": total}


@app.get("/reports/{report_id}")
def get_report(report_id: int):
    """Get a single report by ID."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT r.*, p.platform, p.author, p.url, p.content
           FROM reports r
           JOIN posts p ON r.post_id = p.id
           WHERE r.id = ?""",
        (report_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    r = dict(row)
    for key in ("claims_json", "verdicts_json", "agent_results_json"):
        if r.get(key):
            try:
                r[key] = json.loads(r[key])
            except Exception:
                pass
    return r


@app.get("/stats")
def get_stats():
    """Get dashboard stats."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    total_reports = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

    verdict_counts = conn.execute(
        "SELECT overall_verdict, COUNT(*) as count FROM reports GROUP BY overall_verdict"
    ).fetchall()

    platform_counts = conn.execute(
        "SELECT platform, COUNT(*) as count FROM posts GROUP BY platform"
    ).fetchall()

    recent = conn.execute(
        """SELECT r.overall_verdict, r.confidence, r.created_at, p.platform
           FROM reports r JOIN posts p ON r.post_id = p.id
           ORDER BY r.created_at DESC LIMIT 5"""
    ).fetchall()

    conn.close()

    return {
        "total_reports": total_reports,
        "total_posts": total_posts,
        "verdict_breakdown": [dict(r) for r in verdict_counts],
        "platform_breakdown": [dict(r) for r in platform_counts],
        "recent_reports": [dict(r) for r in recent],
    }


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Analyze a claim manually and return the report."""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    report = analyze_post_with_agents(
        content=req.content,
        source_url=req.source_url,
        platform=req.platform,
        author=req.author,
    )

    if report is None:
        return {"message": "No checkable claims found in the content."}

    verdicts = []
    for v in report.verdicts:
        verdicts.append({
            "claim": v.claim,
            "verdict": v.verdict,
            "explanation": v.explanation,
            "evidence": v.evidence,
        })

    return {
        "overall_verdict": report.overall_verdict,
        "confidence": report.confidence,
        "claims": report.claims,
        "verdicts": verdicts,
        "autopsy_md": report.markdown,
        "agent_results": report.agent_results,
    }