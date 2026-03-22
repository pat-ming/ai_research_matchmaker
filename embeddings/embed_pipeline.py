"""
Faculty embedding pipeline: JSON ingestion → BGE-M3 vectors → Qdrant storage & search.

Uses the same scaled_vector approach from test.py (75% extracted keywords + 25% original),
but self-contained to avoid test.py's module-level side effects.
"""

import json
import os
from pathlib import Path

import numpy as np
import requests
import spacy
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient, models
from qdrant_client.models import PointStruct

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "wustlprof_data_harvest"
QDRANT_PATH = str(PROJECT_ROOT / "db" / "qdrant_data")
JSON_FILES = ["artssci_faculty.json", "mckelvey_faculty.json", "med_faculty.json"]

VECTOR_DIM = 1024
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

# ── Lazy globals (loaded on first use) ─────────────────────────────────────────
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


# ── Embedding functions (same logic as test.py) ───────────────────────────────

def text_vec(text: str | list[str]) -> np.ndarray:
    """Encode text into 1024-dim dense vectors via BGE-M3."""
    model = _get_model()
    if isinstance(text, str):
        return model.encode([text])["dense_vecs"][0]
    return model.encode(text)["dense_vecs"]


def extract_core(text: str) -> dict:
    """Strip buzzwords, extract noun chunks + entities → clean keyword string."""
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
    """75% keyword-extracted vector + 25% original text vector."""
    extracted = extract_core(text)
    vecs = text_vec([extracted["clean_string"], extracted["original"]])
    return 0.75 * vecs[0] + 0.25 * vecs[1]


# ── JSON deduplication ─────────────────────────────────────────────────────────

def deduplicate_faculty(json_data: dict) -> list[dict]:
    """Flatten nested JSON into unique professor records, merging research areas."""
    seen: dict[tuple[str, str], dict] = {}

    for dept_key, dept in json_data.get("departments", {}).items():
        school = dept["school"]
        department = dept["department"]

        for area_name, area in dept.get("research_areas", {}).items():
            for fac in area.get("faculty", []):
                key = (fac["name"], school)

                if key not in seen:
                    seen[key] = {
                        "name": fac["name"],
                        "school": school,
                        "department": department,
                        "profile_url": fac.get("profile_url"),
                        "research": fac.get("research"),
                        "research_interests": list(fac.get("research_interests") or []),
                        "bio": fac.get("bio"),
                        "research_areas": [area_name],
                    }
                else:
                    existing = seen[key]
                    if area_name not in existing["research_areas"]:
                        existing["research_areas"].append(area_name)
                    for interest in fac.get("research_interests") or []:
                        if interest not in existing["research_interests"]:
                            existing["research_interests"].append(interest)
                    if not existing["research"] and fac.get("research"):
                        existing["research"] = fac["research"]
                    if not existing["bio"] and fac.get("bio"):
                        existing["bio"] = fac["bio"]

    return list(seen.values())


def load_all_faculty() -> list[dict]:
    """Load and deduplicate faculty from all JSON files."""
    all_faculty = []
    for filename in JSON_FILES:
        path = DATA_DIR / filename
        if not path.exists():
            print(f"  Skipping {filename} (not found)")
            continue
        with open(path) as f:
            data = json.load(f)
        faculty = deduplicate_faculty(data)
        print(f"  {filename}: {len(faculty)} unique faculty")
        all_faculty.extend(faculty)
    print(f"  Total unique faculty: {len(all_faculty)}")
    return all_faculty


# ── Vector building ────────────────────────────────────────────────────────────

def build_vectors(professor: dict) -> dict:
    """Build named vector dict, omitting null/empty fields."""
    vectors = {}

    if professor.get("research"):
        vectors["research"] = scaled_vector(professor["research"]).tolist()

    if professor.get("research_interests"):
        interests_text = ", ".join(professor["research_interests"])
        vectors["research_interests"] = scaled_vector(interests_text).tolist()

    if professor.get("bio"):
        vectors["bio"] = scaled_vector(professor["bio"]).tolist()

    return vectors


# ── Qdrant operations ─────────────────────────────────────────────────────────

def get_client() -> QdrantClient:
    """Get a Qdrant client (embedded, persists to disk)."""
    os.makedirs(QDRANT_PATH, exist_ok=True)
    return QdrantClient(path=QDRANT_PATH)


def create_collection(client: QdrantClient):
    """Create the faculty collection with 3 named vectors."""
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
        print(f"  Deleted existing '{COLLECTION_NAME}' collection")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "research": models.VectorParams(size=VECTOR_DIM, distance=models.Distance.COSINE),
            "research_interests": models.VectorParams(size=VECTOR_DIM, distance=models.Distance.COSINE),
            "bio": models.VectorParams(size=VECTOR_DIM, distance=models.Distance.COSINE),
        },
    )

    # Payload indices for filtered search
    for field in ["school", "department"]:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    print(f"  Created '{COLLECTION_NAME}' collection with 3 named vectors")


def ingest_all():
    """Full pipeline: load JSONs → deduplicate → embed → upsert into Qdrant."""
    print("Loading faculty data...")
    faculty = load_all_faculty()

    client = get_client()
    print("Setting up Qdrant collection...")
    create_collection(client)

    print("Embedding and upserting faculty...")
    points = []
    skipped = 0

    for i, prof in enumerate(faculty):
        vectors = build_vectors(prof)
        if not vectors:
            skipped += 1
            continue

        point = PointStruct(
            id=i,
            vector=vectors,
            payload={
                "name": prof["name"],
                "school": prof["school"],
                "department": prof["department"],
                "profile_url": prof.get("profile_url"),
                "research_areas": prof.get("research_areas", []),
            },
        )
        points.append(point)

        # Batch upsert every 50 points
        if len(points) >= 50:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"  Upserted {i + 1 - skipped} faculty so far...")
            points = []

    # Final batch
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)

    total = len(faculty) - skipped
    print(f"Done! {total} faculty embedded, {skipped} skipped (no text data)")
    info = client.get_collection(COLLECTION_NAME)
    print(f"Collection '{COLLECTION_NAME}': {info.points_count} points")


# ── Search ─────────────────────────────────────────────────────────────────────

def search(query_text: str, vector_name: str = "research_interests",
           school: str = None, department: str = None, limit: int = 10):
    """Single-vector search with optional metadata filters."""
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


def multi_vector_search(query_text: str, school: str = None,
                        department: str = None, limit: int = 10):
    """Search across all 3 vector spaces, merge with weighted scores."""
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

    # Normalize so professors with fewer vectors aren't penalized
    for entry in merged.values():
        entry["weighted_score"] = entry["raw_score"] / entry["total_weight"]

    ranked = sorted(merged.values(), key=lambda x: x["weighted_score"], reverse=True)
    return ranked[:limit]


# ── Paper lookup (ORCID + OpenAlex) ──────────────────────────────────────────

def get_faculty_orcid(faculty_name: str) -> str | None:
    """Authenticate with ORCID and find a WashU faculty member's ORCID ID."""
    if not ORCID_CLIENT_ID or not ORCID_CLIENT_SECRET:
        print(f"  ORCID credentials missing — skipping {faculty_name}")
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
        print(f"  ORCID auth failed ({auth_resp.status_code}) — skipping {faculty_name}")
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


# ── Combined search: faculty + papers with cosine scoring ────────────────────

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def search_with_papers(query_text: str, school: str = None,
                       department: str = None, limit: int = 10,
                       papers_per_faculty: int = 5):
    """Multi-vector faculty search → ORCID lookup → top papers with cosine scores."""
    print(f"\nMulti-vector search for: \"{query_text}\"")
    query_vec = scaled_vector(query_text)

    faculty_results = multi_vector_search(
        query_text, school=school, department=department, limit=limit,
    )

    if not faculty_results:
        print("  No faculty found.")
        return []

    enriched = []
    for i, fac in enumerate(faculty_results, 1):
        p = fac["payload"]
        name = p["name"]
        print(f"\n  {i}. {name}  (combined: {fac['weighted_score']:.4f})")
        print(f"     {p['department']} — {p['school']}")

        # Look up ORCID
        orcid_id = get_faculty_orcid(name)
        if not orcid_id:
            print(f"     No ORCID found — skipping papers")
            enriched.append({**fac, "papers": []})
            continue

        # Fetch top papers
        papers = get_top_papers(orcid_id, n=papers_per_faculty)
        if not papers:
            print(f"     No papers found on OpenAlex")
            enriched.append({**fac, "papers": []})
            continue

        # Embed paper titles and score against query
        titles = [paper["title"] for paper in papers]
        title_vecs = text_vec(titles)  # batch embed all titles at once

        scored_papers = []
        for paper, tvec in zip(papers, title_vecs):
            score = cosine_sim(query_vec, tvec)
            scored_papers.append({**paper, "compatibility": score})

        scored_papers.sort(key=lambda x: x["compatibility"], reverse=True)

        print(f"     Top Papers:")
        for sp in scored_papers:
            print(f"       {sp['compatibility']:.4f}  {sp['title']}")

        enriched.append({**fac, "papers": scored_papers})

    return enriched


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python embed_pipeline.py ingest                    # Build vector DB from JSONs")
        print('  python embed_pipeline.py search "query"            # Single-vector search')
        print('  python embed_pipeline.py multi "query"             # Multi-vector fusion search')
        print('  python embed_pipeline.py papers "query"            # Faculty search + top papers w/ scores')
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "ingest":
        ingest_all()

    elif cmd == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else "machine learning"
        vec_name = sys.argv[3] if len(sys.argv) > 3 else "research_interests"
        print(f"\nSearching '{vec_name}' for: {query}\n")
        results = search(query, vector_name=vec_name)
        for r in results:
            print(f"  {r.score:.4f}  {r.payload['name']} — {r.payload['department']} ({r.payload['school']})")

    elif cmd == "multi":
        query = sys.argv[2] if len(sys.argv) > 2 else "machine learning"
        print(f"\nMulti-vector search for: {query}\n")
        results = multi_vector_search(query)
        for r in results:
            print(f"  {r['weighted_score']:.4f}  {r['payload']['name']} — {r['payload']['department']} ({r['payload']['school']})")
            for vec, score in r["matches"].items():
                print(f"          {vec}: {score:.4f}")

    elif cmd == "papers":
        query = sys.argv[2] if len(sys.argv) > 2 else "machine learning"
        search_with_papers(query)

    else:
        print(f"Unknown command: {cmd}")
