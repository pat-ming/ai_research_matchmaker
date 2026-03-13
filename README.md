# AI Research Assistant

A tool for exploring Washington University in St. Louis (WashU) faculty research — scrapes academic papers into structured data, harvests professor profiles and research areas, and looks up publications via ORCID and OpenAlex.

## Features

- **PDF Paper Scraper** — Extracts sections, tables, and figures from academic PDFs into structured JSON and Markdown
- **Faculty Data Harvester** — Scrapes WashU CSE faculty research areas, profiles, bios, and lab websites
- **Publication Finder** — Looks up faculty via ORCID, then fetches their publications (title, citations, abstracts, topics) from OpenAlex
- **Vector Embeddings** — Pinecone integration for semantic search over faculty data (work in progress)

## Project Structure

```
├── pdf_compiler/
│   ├── pdf_scraper.py          # PDF → structured JSON/Markdown extraction
│   └── paper_finder.py         # ORCID + OpenAlex publication lookup
├── wustlprof_data_harvest/
│   ├── testplaywright_withcse.py  # Scrapes WashU CSE faculty & lab websites
│   └── data_main.py              # ORCID lookup + OpenAlex paper fetching
├── professor_vector_embedding.py  # Pinecone vector DB setup (WIP)
├── data/                          # Data collection modules
└── api_keys.json                  # API credentials (not committed — see below)
```

## Setup

1. **Clone the repo**
   ```bash
   git clone <repo-url>
   cd AI-Research-Assistant
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install pymupdf pdfplumber pillow playwright beautifulsoup4 requests pinecone pandas numpy
   playwright install chromium
   ```

3. **Create `api_keys.json`** in the project root with your API credentials:
   ```json
   {
     "pinecone_api_key": "your-pinecone-key",
     "openai_api_key": "your-openai-key",
     "openalex_api_key": "your-openalex-key",
     "orcid_client_id": "your-orcid-client-id",
     "orcid_client_secret": "your-orcid-client-secret"
   }
   ```

## Usage

### Scrape a PDF into structured data
```bash
python pdf_compiler/pdf_scraper.py path/to/paper.pdf
```
Outputs a directory with `files.json`, `files.md`, and extracted figures.

### Harvest WashU CSE faculty data
```bash
python wustlprof_data_harvest/testplaywright_withcse.py
```
Scrapes faculty profiles, research areas, and lab websites. Saves to `cse_research_areas.json`.

### Look up a faculty member's publications
```bash
python wustlprof_data_harvest/data_main.py
```
Finds the faculty member's ORCID, fetches their papers from OpenAlex, and exports to CSV.

## API Keys Required

| Key | Service | Purpose |
|-----|---------|---------|
| `pinecone_api_key` | [Pinecone](https://www.pinecone.io/) | Vector database for embeddings |
| `openai_api_key` | [OpenAI](https://platform.openai.com/) | LLM access |
| `openalex_api_key` | [OpenAlex](https://openalex.org/) | Academic paper metadata |
| `orcid_client_id` | [ORCID](https://orcid.org/) | Faculty researcher lookup |
| `orcid_client_secret` | [ORCID](https://orcid.org/) | Faculty researcher lookup |
