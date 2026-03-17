import requests
import json
import os
from pathlib import Path

current_dir = Path(__file__).parent
api_keys_path = current_dir.parent / 'api_keys.json'

with open(api_keys_path, 'r') as file:
    data = json.load(file)

OPENALEX_API_KEY = data.get('openalex_api_key', '')

DOWNLOAD_DIR = current_dir / 'downloads'
DOWNLOAD_DIR.mkdir(exist_ok=True)


def search_openalex(query, per_page=5):
    """Search OpenAlex for papers by title/keyword."""
    url = 'https://api.openalex.org/works'
    params = {
        'search': query,
        'per_page': per_page,
        'api_key': OPENALEX_API_KEY,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get('results', [])


def get_pdf_url(work):
    """Extract the best available PDF URL from an OpenAlex work object."""
    # Try best_oa_location first
    best_oa = work.get('best_oa_location') or {}
    if best_oa.get('pdf_url'):
        return best_oa['pdf_url']

    # Try primary_location
    primary = work.get('primary_location') or {}
    if primary.get('pdf_url'):
        return primary['pdf_url']

    # Try all locations
    for loc in work.get('locations', []):
        if loc.get('pdf_url'):
            return loc['pdf_url']

    # Fall back to oa_url
    oa = work.get('open_access') or {}
    if oa.get('oa_url'):
        return oa['oa_url']

    return None


def download_pdf(pdf_url, filename):
    """Download a PDF from a URL and save it to the downloads directory."""
    filepath = DOWNLOAD_DIR / filename
    headers = {'User-Agent': 'AIResearchAssistant/1.0 (mailto:your@email.com)'}

    response = requests.get(pdf_url, headers=headers, timeout=30, allow_redirects=True)
    response.raise_for_status()

    # Basic check that we got a PDF
    content_type = response.headers.get('Content-Type', '')
    if 'pdf' not in content_type and not response.content[:5] == b'%PDF-':
        print(f"  Warning: Response may not be a PDF (Content-Type: {content_type})")

    with open(filepath, 'wb') as f:
        f.write(response.content)

    size_kb = len(response.content) / 1024
    print(f"  Saved: {filepath} ({size_kb:.1f} KB)")
    return filepath


def search_and_download(query, max_results=5):
    """Search for papers and attempt to download available PDFs."""
    print(f"Searching OpenAlex for: '{query}'")
    results = search_openalex(query, per_page=max_results)
    print(f"Found {len(results)} results\n")

    for i, work in enumerate(results, 1):
        title = work.get('title', 'Untitled')
        doi = (work.get('ids') or {}).get('doi', 'No DOI')
        is_oa = (work.get('open_access') or {}).get('is_oa', False)
        pdf_url = get_pdf_url(work)

        print(f"[{i}] {title}")
        print(f"    DOI: {doi}")
        print(f"    Open Access: {is_oa}")
        print(f"    PDF URL: {pdf_url or 'None found'}")

        if pdf_url:
            # Create a safe filename from the title
            safe_title = "".join(c if c.isalnum() or c in ' -_' else '' for c in title)
            safe_title = safe_title[:80].strip()
            filename = f"{safe_title}.pdf"

            try:
                download_pdf(pdf_url, filename)
            except Exception as e:
                print(f"  Download failed: {e}")
        print()


if __name__ == '__main__':
    search_and_download('neural ordinary differential equations', max_results=5)
