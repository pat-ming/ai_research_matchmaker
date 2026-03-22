# AI Research Assistant — Full Implementation Plan

## Context

The project scrapes WashU STEM faculty profiles (~1,584 faculty across Arts & Sciences, McKelvey Engineering, and School of Medicine), fetches publications via ORCID/OpenAlex, and extracts structured data from PDFs. The vector embedding pipeline (Pinecone + OpenAI) is WIP but relies on paid APIs.

**Goals:**
1. Add **RAG Q&A** and **Faculty-Research Matching** without paid APIs
2. Use **SQLite** for structured faculty/paper data
3. Build a **simple search website** (text box → results)
4. Design for **future scaling** to all WashU STEM faculty (not just CSE)

**Hardware:** 8GB RAM Mac (Apple Silicon)

### What We're Replacing
- **OpenAI API** → **Ollama** (local) and/or **Groq** (free cloud) — swappable
- **Pinecone** → **Qdrant** (local vector DB with named vectors, $0)

### What We're Keeping
- **BGE-M3** embeddings (`embeddings/test.py`) — top-tier, runs on MPS
- **OpenAlex / ORCID / Europe PMC** APIs — free academic data
- Existing scraping code in `pdf_compiler/` and `wustlprof_data_harvest/`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  FastAPI Web App                  │
│          (simple search interface)                │
│    /search   /match   /ask   /faculty/:id        │
└──────────┬───────────┬──────────┬────────────────┘
           │           │          │
     ┌─────▼─────┐ ┌──▼───┐ ┌───▼────┐
     │ Research   │ │ RAG  │ │ Search │
     │ Matcher    │ │ Q&A  │ │ Engine │
     └─────┬─────┘ └──┬───┘ └───┬────┘
           │           │         │
     ┌─────▼───────────▼─────────▼─────┐
     │       EmbeddingPipeline          │
     │    BGE-M3 + Qdrant (vectors)     │
     └─────────────┬───────────────────┘
                   │
     ┌─────────────▼───────────────────┐
     │     SQLite (structured data)     │
     │  faculty, papers, departments    │
     └─────────────────────────────────┘
                   │
     ┌─────────────▼───────────────────┐
     │        LLM Client               │
     │   Ollama (local) or Groq (cloud)│
     └─────────────────────────────────┘
```

**Two databases, each doing what it's best at:**
- **SQLite** — structured queries: "list all CS faculty," filter by department, sort by citations, faculty profiles
- **Qdrant** — semantic search with named vectors (research, research_interests, bio per faculty): "who works on topics similar to autonomous vehicles?"

---

## Implementation Plan

### Step 1: SQLite Database Schema

**File:** `db/database.py` (new)

SQLite stores all structured faculty and paper data. This replaces reading JSON/CSV files directly and makes the system scale-ready.

```sql
-- Faculty table
CREATE TABLE faculty (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT,           -- "CSE", "BME", "Physics", etc.
    school TEXT,               -- "McKelvey Engineering", "Arts & Sciences", etc.
    profile_url TEXT,
    lab_website TEXT,
    research_summary TEXT,     -- scraped research description
    bio TEXT,
    orcid_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Papers table
CREATE TABLE papers (
    id INTEGER PRIMARY KEY,
    faculty_id INTEGER REFERENCES faculty(id),
    title TEXT NOT NULL,
    abstract TEXT,
    citations INTEGER DEFAULT 0,
    date TEXT,
    subfield TEXT,
    topic TEXT,
    doi TEXT,
    journal TEXT,
    open_access BOOLEAN,
    oa_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Research areas (many-to-many)
CREATE TABLE research_areas (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE faculty_research_areas (
    faculty_id INTEGER REFERENCES faculty(id),
    area_id INTEGER REFERENCES research_areas(id),
    PRIMARY KEY (faculty_id, area_id)
);
```

This module provides:
- `init_db()` — create tables if they don't exist
- `import_from_json(json_path)` — import existing `cse_research_areas.json`
- `import_from_csv(csv_path, faculty_name)` — import paper CSVs
- `get_faculty(id)`, `search_faculty(name)`, `get_papers(faculty_id)` — basic queries

**Why SQLite over just JSON/CSV:** As you scale to hundreds of STEM faculty with thousands of papers, you need filtering (by department, citations, date), joins (faculty ↔ papers), and indexed search. SQLite handles this with zero setup. The `school` and `department` columns are ready for when you expand beyond CSE.

### Step 2: LLM Client (Ollama + Groq)

**File:** `llm/llm_client.py` (new)

Unified interface — the rest of the code calls `llm.generate(prompt)` without caring which backend is active:

```python
class LLMClient:
    def __init__(self, backend="groq", model=None):
        self.backend = backend  # "ollama" or "groq"
        self.model = model or ("llama3.2:3b" if backend == "ollama" else "llama-3.1-70b-versatile")

    def generate(self, prompt):
        if self.backend == "ollama":
            # POST to http://localhost:11434/api/generate
        elif self.backend == "groq":
            # POST to https://api.groq.com/openai/v1/chat/completions (uses groq_api_key)
```

**Ollama setup** (optional, for offline use):
```bash
brew install ollama && ollama pull llama3.2:3b
```

**Groq setup** (recommended to start — more powerful, no local RAM cost):
- Sign up at console.groq.com (free tier: ~30 req/min)
- Add `groq_api_key` to `api_keys.json`

### Step 3: Embedding Pipeline + Qdrant

**File:** `embeddings/embed_pipeline.py` (new — already created)

Extends `embeddings/test.py` into a full ingestion + search pipeline using Qdrant with named vectors:

- **3 named vectors per faculty point** (1024-dim, cosine): `research`, `research_interests`, `bio`
- Vectors only included when source field is non-null (Qdrant skips missing vectors during queries)
- Payload metadata: `name`, `school`, `department`, `profile_url`, `research_areas`
- Deduplicates faculty across research areas by `(name, school)`, merging research areas
- Single-vector search (`search()`) and multi-vector fusion search (`multi_vector_search()`)
- Payload indices on `school` and `department` for filtered queries

**Qdrant collection:** `faculty` — one point per unique professor with up to 3 named vectors + metadata payload.

**Data flow:** JSON scrapers → `embed_pipeline.py ingest` → Qdrant (vectors + metadata on disk at `db/qdrant_data/`).

### Step 4: RAG Q&A System

**File:** `rag/query_engine.py` (new)

```python
class ResearchQA:
    def __init__(self, embedding_pipeline, llm_client, db):
        self.pipeline = embedding_pipeline
        self.llm = llm_client
        self.db = db  # SQLite connection — to fetch full faculty/paper details

    def ask(self, question, n_context=5):
        # 1. Semantic search: embed question → query Qdrant
        faculty_hits = self.pipeline.search(question, "faculty_profiles", n_context)
        paper_hits = self.pipeline.search(question, "paper_abstracts", n_context)

        # 2. Enrich with SQLite: get full faculty profiles + paper details for the hits
        context = self._build_context(faculty_hits, paper_hits)

        # 3. Generate answer via LLM
        prompt = f"""Based on the following WashU faculty and publication data, answer the question.
Context:
{context}
Question: {question}
Answer with specific faculty names, paper titles, and details. Only use information from the context."""

        return self.llm.generate(prompt)
```

The SQLite enrichment step is key — Qdrant returns the matched text + metadata IDs, then we pull full details (all papers, department, profile URL, etc.) from SQLite to build a rich context for the LLM.

### Step 5: Faculty-Research Matching

**File:** `rag/research_matcher.py` (new)

```python
class ResearchMatcher:
    def __init__(self, embedding_pipeline, llm_client, db):
        self.pipeline = embedding_pipeline
        self.llm = llm_client
        self.db = db

    def match(self, interest_description, n_results=10):
        """
        Input: "I'm interested in using deep learning for medical image analysis"
        Output: Ranked list of faculty with scores, departments, and top papers
        """
        # 1. Search faculty_profiles collection
        # 2. Search paper_abstracts collection
        # 3. Aggregate: composite score per faculty (profile similarity + best paper similarity)
        # 4. Enrich from SQLite: department, profile URL, top papers
        # 5. Return ranked results

    def match_with_explanation(self, interest_description, n_results=5):
        """Uses LLM to explain WHY each faculty member is a good match"""
```

### Step 6: FastAPI Web App

**File:** `web/app.py` (new)

Simple search website with a few endpoints:

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

@app.get("/")
async def home():
    """Serves the search page (HTML with a text box)"""

@app.get("/api/search")
async def search(q: str):
    """Semantic search — returns ranked faculty + papers"""

@app.get("/api/match")
async def match(interests: str):
    """Faculty-research matching — returns ranked faculty with scores"""

@app.get("/api/ask")
async def ask(question: str):
    """RAG Q&A — returns LLM-generated answer"""

@app.get("/api/faculty/{faculty_id}")
async def faculty_detail(faculty_id: int):
    """Faculty profile — info + papers from SQLite"""
```

**Frontend:** `web/static/index.html` — single-page HTML with:
- Search box (text input)
- Toggle between "Search", "Match", and "Ask" modes
- Results displayed as cards (faculty name, department, relevance score, top papers)
- Click a faculty card → shows full profile with all papers

Minimal CSS, no build tools, no React/Vue — just HTML + vanilla JS + fetch() calls to the API. Can be enhanced later.

```bash
# Run the web app:
uvicorn web.app:app --reload
# Opens at http://localhost:8000
```

### Step 7: CLI Entry Point

**File:** `main.py` (rewrite)

```python
# Usage:
# python main.py ingest              # Import data → SQLite + Qdrant
# python main.py search "query"      # Semantic search (CLI)
# python main.py match "interests"   # Faculty matching (CLI)
# python main.py ask "question"      # RAG Q&A (CLI)
# python main.py serve               # Start web app (FastAPI)
```

---

## Scaling to All WashU STEM

The architecture is ready for this. When you expand:

1. **Add new scrapers** in `wustlprof_data_harvest/` for other departments (BME, Physics, Math, etc.) — they all write to the same SQLite `faculty` table with different `department` and `school` values
2. **Re-run ingestion** (`python main.py ingest`) — rebuilds Qdrant from SQLite
3. **No code changes needed** in the RAG/matching/web layers — they query SQLite + Qdrant generically

**Scale estimates:**
- All WashU STEM: ~500-1,000 faculty, ~20,000-50,000 papers
- SQLite handles millions of rows easily
- Qdrant handles ~1M vectors without issue
- BGE-M3 embedding speed: ~100 texts/sec on MPS

The `data/arts_sci.py` and `data/mckelvey.py` placeholder files you already have are where future scrapers would go.

---

## Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `db/database.py` | New | SQLite schema + CRUD operations |
| `llm/llm_client.py` | New | Unified LLM interface (Ollama + Groq) |
| `embeddings/embed_pipeline.py` | New (done) | BGE-M3 + Qdrant pipeline with named vectors |
| `rag/query_engine.py` | New | RAG Q&A system |
| `rag/research_matcher.py` | New | Faculty-research matching |
| `web/app.py` | New | FastAPI web server |
| `web/static/index.html` | New | Search interface (HTML + JS) |
| `main.py` | Rewrite | CLI entry point |
| `professor_vector_embedding.py` | Delete | Replaced by embeddings/embed_pipeline.py |
| `requirements.txt` | New | Pin dependencies |

**New dependencies:** `qdrant-client`, `groq`, `fastapi`, `uvicorn`, `ollama` (optional)

---

## Hardware Notes (8GB RAM)

- **BGE-M3** ~2GB on MPS — works fine
- **Qdrant + SQLite** — lightweight, disk-based (Qdrant embedded mode, no server)
- **Groq** (recommended start) — zero local RAM cost, Llama 3.1 70B quality
- **Ollama `llama3.2:3b`** (~2GB) — for offline use, tight but workable alongside BGE-M3
- **Strategy:** Ingestion and querying are separate steps. During ingestion, only BGE-M3 is loaded. During Q&A, Qdrant loads from disk and LLM handles generation.

---

## Verification

1. `python main.py ingest` — imports existing JSON/CSV into SQLite, builds Qdrant vectors
2. `python main.py search "machine learning"` — verify semantic search returns relevant faculty
3. `python main.py match "deep learning for healthcare"` — verify matching returns ranked faculty
4. `python main.py ask "Which professors work on cybersecurity?"` — test full RAG pipeline
5. `python main.py serve` → open `http://localhost:8000` → test search, match, and ask from the web UI
6. Cross-check RAG answers against `cse_research_areas.json` for accuracy
