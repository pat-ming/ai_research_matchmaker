# AI Research Assistant

A full-stack platform for discovering Washington University in St. Louis (WashU) STEM faculty and their research. Scrapes professor profiles from 19 departments, embeds them with BGE-M3 vectors, and serves a semantic search interface powered by FastAPI and Next.js.

## Features

- **Multi-Department Faculty Scraping** — Playwright-based scrapers for 19 WashU STEM departments across McKelvey Engineering, Arts & Sciences, and the School of Medicine
- **Semantic Search** — BGE-M3 embeddings (1024-dim) stored in a local Qdrant vector database with multi-vector search (research, research interests, bio)
- **Publication Enrichment** — ORCID + OpenAlex integration to fetch faculty publications, citations, and abstracts in real time
- **Modern Web Interface** — Next.js 16 + React 19 frontend with dark mode, school/department filtering, and animated result cards
- **PDF Paper Scraper** — Extracts sections, tables, and figures from academic PDFs into structured JSON and Markdown

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 |
| Backend | FastAPI, Uvicorn |
| Embeddings | BGE-M3 (FlagEmbedding), spaCy |
| Vector DB | Qdrant (embedded, disk-persisted) |
| Scraping | Playwright, BeautifulSoup4 |
| PDF Processing | PyMuPDF, pdfplumber |
| External APIs | ORCID, OpenAlex |

## Project Structure

```
├── main.py                          # Entry point — launches API + frontend
├── api/
│   └── server.py                    # FastAPI search endpoint + paper enrichment
├── embeddings/
│   ├── embed_pipeline.py            # Faculty JSON → Qdrant ingestion pipeline
│   ├── search_faculty.py            # Qdrant query utilities + ORCID lookup
│   └── test.py                      # Embedding proof-of-concept
├── db/
│   └── qdrant_data/                 # Persisted Qdrant vector database
├── wustlprof_data_harvest/
│   ├── washu_stem_scraper.py        # CLI entry point for all 19 dept scrapers
│   ├── scraper_engineering.py       # McKelvey Engineering (CSE, BME, ESE, EECE, MEMS)
│   ├── scraper_artssci.py           # Arts & Sciences (Physics, Chem, Bio, Math, …)
│   ├── scraper_med.py               # School of Medicine (Genetics, Neuro, Biochem, …)
│   ├── scraper_utils.py             # Shared scraping utilities
│   ├── artssci_faculty.json         # Scraped Arts & Sciences data
│   ├── mckelvey_faculty.json        # Scraped Engineering data
│   └── med_faculty.json             # Scraped Medicine data
├── pdf_compiler/
│   ├── pdf_scraper.py               # PDF → structured JSON/Markdown extraction
│   ├── paper_finder.py              # ORCID + OpenAlex publication lookup
│   └── pdf_downloader.py            # Batch paper downloader
├── research-matchmaker/             # Next.js frontend
│   ├── app/
│   │   ├── page.tsx                 # Main search interface
│   │   ├── layout.tsx               # Root layout
│   │   └── globals.css              # Tailwind + animations
│   ├── package.json
│   └── tsconfig.json
└── api_keys.json                    # API credentials (not committed)
```

## Setup

1. **Clone the repo**
   ```bash
   git clone <repo-url>
   cd AI-Research-Assistant
   ```

2. **Install Python dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install fastapi uvicorn qdrant-client FlagEmbedding spacy \
       playwright beautifulsoup4 requests pymupdf pdfplumber pillow pandas numpy
   python -m spacy download en_core_web_md
   playwright install chromium
   ```

3. **Install frontend dependencies**
   ```bash
   cd research-matchmaker
   npm install
   cd ..
   ```

4. **Create `api_keys.json`** in the project root:
   ```json
   {
     "openalex_api_key": "your-openalex-key",
     "orcid_client_id": "your-orcid-client-id",
     "orcid_client_secret": "your-orcid-client-secret"
   }
   ```

5. **Run the embedding pipeline** (first time only)
   ```bash
   python embeddings/embed_pipeline.py
   ```

## Usage

### Start the application
```bash
python main.py          # Start both API (port 8000) + frontend (port 3000)
python main.py api      # Start only the API server
python main.py web      # Start only the Next.js dev server
```

Then open **http://localhost:3000** in your browser.

### Scrape faculty data
```bash
python wustlprof_data_harvest/washu_stem_scraper.py all            # All 19 departments
python wustlprof_data_harvest/washu_stem_scraper.py engineering     # McKelvey only
python wustlprof_data_harvest/washu_stem_scraper.py cse             # Single department
```

### Process a PDF paper
```bash
python pdf_compiler/pdf_scraper.py path/to/paper.pdf
```

### Look up faculty publications
```bash
python wustlprof_data_harvest/data_main.py
```

## Architecture

```
WashU STEM Websites (19 departments)
            │
            │  Playwright + BeautifulSoup
            ▼
    Faculty Scrapers ──► JSON files (per school)
            │
            │  embed_pipeline.py + BGE-M3
            ▼
    Qdrant Vector DB (3 named vectors per faculty)
            │
            ▼
    FastAPI Backend ◄──► ORCID / OpenAlex APIs
            │
            ▼
    Next.js Frontend (localhost:3000)
```

## Departments Covered

| School | Departments |
|--------|-------------|
| **McKelvey Engineering** | CSE, BME, ESE, EECE, MEMS |
| **Arts & Sciences** | Physics, Chemistry, Biology, Math, Earth & Environmental Sciences, Materials Science & Engineering, Philosophy-Neuroscience-Psychology, Psychological & Brain Sciences |
| **School of Medicine** | Genetics, Neuroscience, Biochemistry & Molecular Biophysics, Cell Biology & Physiology, Developmental Biology, Molecular Microbiology |

## API Keys Required

| Key | Service | Purpose |
|-----|---------|---------|
| `openalex_api_key` | [OpenAlex](https://openalex.org/) | Academic paper metadata |
| `orcid_client_id` | [ORCID](https://orcid.org/) | Faculty researcher lookup |
| `orcid_client_secret` | [ORCID](https://orcid.org/) | Faculty researcher lookup |
