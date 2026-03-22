"""
Search the faculty vector DB for professors matching a student's research interests.

Edit the query variables at the bottom, then hit Run in VS Code.
"""

import json
from pathlib import Path

import numpy as np
import requests
import spacy
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient, models

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
QDRANT_PATH = str(PROJECT_ROOT / "db" / "qdrant_data")
COLLECTION_NAME = "faculty"

# ── ORCID credentials ────────────────────────────────────────────────────────
_api_keys_path = PROJECT_ROOT / "api_keys.json"
if _api_keys_path.exists():
    with open(_api_keys_path) as _f:
        _api_keys = json.load(_f)
    ORCID_CLIENT_ID = _api_keys.get("orcid_client_id", "").strip()
    ORCID_CLIENT_SECRET = _api_keys.get("orcid_client_secret", "").strip()
else:
    ORCID_CLIENT_ID = ""
    ORCID_CLIENT_SECRET = ""

# ── Lazy globals ───────────────────────────────────────────────────────────────
_nlp = None
_model = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_md")
    return _nlp


def _get_model():
    global _model
    if _model is None:
        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, device="mps")
    return _model


# ── Embedding functions (same as test.py) ──────────────────────────────────────

def text_vec(text: str | list[str]) -> np.ndarray:
    model = _get_model()
    if isinstance(text, str):
        return model.encode([text])["dense_vecs"][0]
    return model.encode(text)["dense_vecs"]


def extract_core(text: str) -> dict:
    nlp = _get_nlp()
    doc = nlp(text)
    keywords = [
        chunk.text for chunk in doc.noun_chunks
        if not any(pron == chunk.root.lemma_.lower() for pron in ["i", "me", "my"])
    ]
    entities = [ent.text for ent in doc.ents]
    combined = keywords + entities
    unique = []
    for item in combined:
        if item not in unique:
            unique.append(item)
    return {
        "original": text,
        "core_concepts": unique,
        "clean_string": " ".join(unique),
    }


def scaled_vector(text: str) -> np.ndarray:
    extracted = extract_core(text)
    vecs = text_vec([extracted["clean_string"], extracted["original"]])
    return 0.75 * vecs[0] + 0.25 * vecs[1]


# ── Qdrant search ─────────────────────────────────────────────────────────────

def get_client() -> QdrantClient:
    return QdrantClient(path=QDRANT_PATH)


def search(query_text, vector_name="research_interests", school=None, department=None, limit=10):
    client = get_client()
    query_vec = scaled_vector(query_text).tolist()

    filter_conditions = []
    if school:
        filter_conditions.append(
            models.FieldCondition(key="school", match=models.MatchValue(value=school))
        )
    if department:
        filter_conditions.append(
            models.FieldCondition(key="department", match=models.MatchValue(value=department))
        )
    query_filter = models.Filter(must=filter_conditions) if filter_conditions else None

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vec,
        using=vector_name,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    return results.points


def multi_vector_search(query_text, school=None, department=None, limit=10):
    client = get_client()
    query_vec = scaled_vector(query_text).tolist()

    weights = {"research": 0.4, "research_interests": 0.35, "bio": 0.25}

    filter_conditions = []
    if school:
        filter_conditions.append(
            models.FieldCondition(key="school", match=models.MatchValue(value=school))
        )
    if department:
        filter_conditions.append(
            models.FieldCondition(key="department", match=models.MatchValue(value=department))
        )
    query_filter = models.Filter(must=filter_conditions) if filter_conditions else None

    merged = {}
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

    # Normalize: divide by total weight so professors with fewer vectors aren't penalized
    for entry in merged.values():
        entry["weighted_score"] = entry["raw_score"] / entry["total_weight"]

    ranked = sorted(merged.values(), key=lambda x: x["weighted_score"], reverse=True)
    return ranked[:limit]


# ══════════════════════════════════════════════════════════════════════════════

def main(query, vector="research_interests", school=None, department=None, limit=10, use_multi=False):
    if use_multi:
        print(f"\nMulti-vector search for: \"{query}\"")
        print(f"  Weights: research=0.4, research_interests=0.35, bio=0.25")
        if school: print(f"  School: {school}")
        if department: print(f"  Department: {department}")

        results = multi_vector_search(query, school=school, department=department, limit=limit)
        if not results:
            print("\n  No results found.")
        else:
            for i, r in enumerate(results, 1):
                p = r["payload"]
                print(f"\n  {i}. {p['name']}  (combined: {r['weighted_score']:.4f})")
                print(f"     {p['department']} — {p['school']}")
                if p.get("profile_url"): print(f"     {p['profile_url']}")
                if p.get("research_areas"): print(f"     Areas: {', '.join(p['research_areas'])}")
                for vec_name, score in r["matches"].items():
                    print(f"       {vec_name}: {score:.4f}")
    else:
        print(f"\nSearching '{vector}' for: \"{query}\"")
        if school: print(f"  School: {school}")
        if department: print(f"  Department: {department}")

        results = search(query, vector_name=vector, school=school, department=department, limit=limit)
        if not results:
            print("\n  No results found.")
        else:
            for i, r in enumerate(results, 1):
                p = r.payload
                print(f"\n  {i}. {p['name']}  (score: {r.score:.4f})")
                print(f"     {p['department']} — {p['school']}")
                if p.get("profile_url"): print(f"     {p['profile_url']}")
                if p.get("research_areas"): print(f"     Areas: {', '.join(p['research_areas'])}")

    print()


# ── Paper lookup (ORCID + OpenAlex) ──────────────────────────────────────────

def get_faculty_orcid(faculty_name: str) -> str | None:
    """Authenticate with ORCID and find a WashU faculty member's ORCID ID."""
    if not ORCID_CLIENT_ID or not ORCID_CLIENT_SECRET:
        print(f"    ORCID credentials missing — skipping {faculty_name}")
        return None

    auth_resp = requests.post(
        "https://orcid.org/oauth/token",
        data={
            "client_id": ORCID_CLIENT_ID,
            "client_secret": ORCID_CLIENT_SECRET,
            "scope": "/read-public",
            "grant_type": "client_credentials",
        },
        headers={"Accept": "application/json"},
    )
    if auth_resp.status_code != 200:
        return None

    token = auth_resp.json().get("access_token")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    search_resp = requests.get(
        "https://pub.orcid.org/v3.0/expanded-search/",
        params={"q": f'"{faculty_name}"', "rows": 25},
        headers=headers,
    )
    results = search_resp.json().get("expanded-result") or []

    washu_variants = ["washington university", "wustl", "washu", "bjc", "st. louis"]
    for person in results:
        inst_text = " ".join(person.get("institution-name", [])).lower()
        if any(v in inst_text for v in washu_variants):
            return person.get("orcid-id")

    return None


def get_top_papers(orcid_id: str, n: int = 5) -> list[dict]:
    """Fetch top N papers by citation count from OpenAlex for a given ORCID."""
    url = (
        f"https://api.openalex.org/works?"
        f"filter=authorships.author.orcid:https://orcid.org/{orcid_id}"
        f"&sort=cited_by_count:desc&per_page={n}"
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
            })
    return papers


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ══════════════════════════════════════════════════════════════════════════════

def main_with_papers(query, school=None, department=None, limit=10, papers_per_faculty=5):
    """Multi-vector faculty search → ORCID lookup → top papers with cosine scores."""
    print(f"\nMulti-vector search for: \"{query}\"")
    print(f"  Weights: research=0.4, research_interests=0.35, bio=0.25")
    if school: print(f"  School: {school}")
    if department: print(f"  Department: {department}")

    query_vec = scaled_vector(query)

    results = multi_vector_search(query, school=school, department=department, limit=limit)
    if not results:
        print("\n  No results found.")
        return []

    enriched = []
    for i, fac in enumerate(results, 1):
        p = fac["payload"]
        name = p["name"]
        print(f"\n  {i}. {name}  (combined: {fac['weighted_score']:.4f})")
        print(f"     {p['department']} — {p['school']}")
        if p.get("profile_url"): print(f"     {p['profile_url']}")
        if p.get("research_areas"): print(f"     Areas: {', '.join(p['research_areas'])}")
        for vec_name, score in fac["matches"].items():
            print(f"       {vec_name}: {score:.4f}")

        # Look up ORCID → papers
        orcid_id = get_faculty_orcid(name)
        if not orcid_id:
            print(f"     Papers: No ORCID found — skipping")
            enriched.append({**fac, "papers": []})
            continue

        papers = get_top_papers(orcid_id, n=papers_per_faculty)
        if not papers:
            print(f"     Papers: None found on OpenAlex")
            enriched.append({**fac, "papers": []})
            continue

        # Batch embed paper titles, score against query
        titles = [paper["title"] for paper in papers]
        title_vecs = text_vec(titles)

        scored_papers = []
        for paper, tvec in zip(papers, title_vecs):
            score = cosine_sim(query_vec, tvec)
            scored_papers.append({**paper, "compatibility": score})

        scored_papers.sort(key=lambda x: x["compatibility"], reverse=True)

        print(f"     Top Papers:")
        for sp in scored_papers:
            print(f"       {sp['compatibility']:.4f}  {sp['title']}")

        enriched.append({**fac, "papers": scored_papers})

    print()
    return enriched


# ══════════════════════════════════════════════════════════════════════════════
#  EDIT YOUR QUERY HERE, THEN HIT RUN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main_with_papers("I'm interested in developping learning-based computer vision algorithms, with a focus on geospatial and medical applications")

