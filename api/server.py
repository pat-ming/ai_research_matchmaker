"""
FastAPI server wrapping the faculty vector search + paper lookup pipeline.

Run:  python api/server.py          (starts on http://localhost:8000)
      uvicorn api.server:app --reload  (from project root)
"""

import sys
from pathlib import Path

# ── Make embeddings/ importable ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from embeddings.search_faculty import (
    get_client,
    get_faculty_orcid,
    get_top_papers,
    cosine_sim,
    scaled_vector,
    text_vec,
    COLLECTION_NAME,
)
from qdrant_client import models

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="WashU Research Matchmaker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── School name mapping (frontend display → Qdrant payload value) ────────────
SCHOOL_MAP = {
    "McKelvey": "McKelvey Engineering",
    "Arts & Sciences": "Arts & Sciences",
    "WashU Med": "School of Medicine",
}


# ── Request / Response models ────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str
    school: str | None = None
    departments: list[str] | None = None
    limit: int = 10
    papers_per_faculty: int = 5


class PaperResult(BaseModel):
    title: str
    citations: int
    doi: str | None
    date: str | None
    compatibility: float


class FacultyResult(BaseModel):
    rank: int
    name: str
    department: str
    school: str
    profile_url: str | None
    research_areas: list[str]
    weighted_score: float
    matches: dict[str, float]
    papers: list[PaperResult]
    recent_papers: list[PaperResult]


class SearchResponse(BaseModel):
    query: str
    results: list[FacultyResult]


# ── Multi-department search (OR logic) ───────────────────────────────────────
def multi_vector_search_multi_dept(
    query_text: str,
    school: str | None = None,
    departments: list[str] | None = None,
    limit: int = 10,
):
    """Search across all 3 vector spaces with school + multi-department filters."""
    client = get_client()
    query_vec = scaled_vector(query_text).tolist()

    weights = {"research": 0.4, "research_interests": 0.35, "bio": 0.25}

    # Build filter conditions
    must_conditions = []
    if school:
        qdrant_school = SCHOOL_MAP.get(school, school)
        must_conditions.append(
            models.FieldCondition(
                key="school", match=models.MatchValue(value=qdrant_school)
            )
        )
    if departments:
        # OR across departments using MatchAny
        must_conditions.append(
            models.FieldCondition(
                key="department", match=models.MatchAny(any=departments)
            )
        )

    query_filter = models.Filter(must=must_conditions) if must_conditions else None

    merged: dict[int, dict] = {}

    for vec_name, weight in weights.items():
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vec,
            using=vec_name,
            query_filter=query_filter,
            limit=limit * 2,
            with_payload=True,
        )
        for point in results.points:
            if point.id not in merged:
                merged[point.id] = {
                    "payload": point.payload,
                    "raw_score": point.score * weight,
                    "total_weight": weight,
                    "matches": {vec_name: point.score},
                }
            else:
                merged[point.id]["raw_score"] += point.score * weight
                merged[point.id]["total_weight"] += weight
                merged[point.id]["matches"][vec_name] = point.score

    for entry in merged.values():
        entry["weighted_score"] = entry["raw_score"] / entry["total_weight"]

    ranked = sorted(merged.values(), key=lambda x: x["weighted_score"], reverse=True)
    return ranked[:limit]


# ── Fetch recent papers by date ───────────────────────────────────────────────
def get_recent_papers(orcid_id: str, n: int = 5) -> list[dict]:
    """Fetch top N most recent papers from OpenAlex for a given ORCID."""
    url = (
        f"https://api.openalex.org/works?"
        f"filter=authorships.author.orcid:https://orcid.org/{orcid_id}"
        f"&sort=publication_date:desc&per_page={n}"
    )
    resp = requests.get(url)
    if resp.status_code != 200:
        return []

    papers = []
    for work in resp.json().get("results", []):
        title = work.get("title")
        if title:
            papers.append({
                "title": title,
                "citations": work.get("cited_by_count", 0),
                "doi": work.get("ids", {}).get("doi"),
                "date": work.get("publication_date"),
            })
    return papers


# ── Endpoint ─────────────────────────────────────────────────────────────────
@app.post("/search", response_model=SearchResponse)
def search_faculty(req: SearchRequest):
    """Faculty search → ORCID lookup → top papers with cosine compatibility scores."""
    query_vec = scaled_vector(req.query)

    faculty_results = multi_vector_search_multi_dept(
        req.query,
        school=req.school,
        departments=req.departments,
        limit=req.limit,
    )

    enriched: list[FacultyResult] = []

    for i, fac in enumerate(faculty_results, 1):
        p = fac["payload"]
        name = p["name"]

        papers_out: list[PaperResult] = []
        recent_out: list[PaperResult] = []
        orcid_id = get_faculty_orcid(name)

        if orcid_id:
            # Top papers by citations
            raw_papers = get_top_papers(orcid_id, n=req.papers_per_faculty)
            # Recent papers by date
            raw_recent = get_recent_papers(orcid_id, n=req.papers_per_faculty)

            # Batch embed all unique titles at once
            all_titles = []
            cited_titles = [p["title"] for p in raw_papers] if raw_papers else []
            recent_titles = [p["title"] for p in raw_recent] if raw_recent else []
            all_titles = cited_titles + [t for t in recent_titles if t not in cited_titles]

            title_vec_map: dict[str, np.ndarray] = {}
            if all_titles:
                vecs = text_vec(all_titles)
                for title, vec in zip(all_titles, vecs):
                    title_vec_map[title] = vec

            # Score cited papers
            if raw_papers:
                for paper in raw_papers:
                    tvec = title_vec_map.get(paper["title"])
                    score = cosine_sim(query_vec, tvec) if tvec is not None else 0.0
                    papers_out.append(PaperResult(
                        title=paper["title"],
                        citations=paper["citations"],
                        doi=paper.get("doi"),
                        date=paper.get("date"),
                        compatibility=round(score, 4),
                    ))
                papers_out.sort(key=lambda x: x.compatibility, reverse=True)

            # Score recent papers
            if raw_recent:
                for paper in raw_recent:
                    tvec = title_vec_map.get(paper["title"])
                    score = cosine_sim(query_vec, tvec) if tvec is not None else 0.0
                    recent_out.append(PaperResult(
                        title=paper["title"],
                        citations=paper["citations"],
                        doi=paper.get("doi"),
                        date=paper.get("date"),
                        compatibility=round(score, 4),
                    ))

        enriched.append(
            FacultyResult(
                rank=i,
                name=name,
                department=p.get("department", ""),
                school=p.get("school", ""),
                profile_url=p.get("profile_url"),
                research_areas=p.get("research_areas", []),
                weighted_score=round(fac["weighted_score"], 4),
                matches={k: round(v, 4) for k, v in fac["matches"].items()},
                papers=papers_out,
                recent_papers=recent_out,
            )
        )

    return SearchResponse(query=req.query, results=enriched)


# ── Run directly ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
