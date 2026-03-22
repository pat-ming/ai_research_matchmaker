"""
Scraper for WashU School of Medicine basic science departments.

Med school departments use WordPress with card-based faculty directories:
- Faculty listed on /people/ or /people-page/faculty/ with pagination
- Profile URLs follow /faculty/last-name-first-name/ pattern
- Research areas on /research/ pages
- Different CSS from both Engineering and A&S templates

Initial departments (basic science): Genetics, Neuroscience, Biochemistry,
Cell Biology, Developmental Biology, Molecular Microbiology.
Extensible to all 21 departments by adding entries to MED_DEPTS.
"""

from playwright.sync_api import Playwright
import requests
from bs4 import BeautifulSoup
import time

from scraper_utils import (
    HEADERS,
    REQUEST_DELAY,
    safe_goto,
    scrape_all_lab_websites,
    enrich_from_profiles_portal,
)

MED_DEPTS = {
    # Basic science departments (initial)
    "genetics": {
        "name": "Genetics",
        "school": "School of Medicine",
        "base_url": "https://genetics.wustl.edu",
        "people_url": "https://genetics.wustl.edu/people/",
        "research_url": "https://genetics.wustl.edu/research/",
    },
    "neuroscience": {
        "name": "Neuroscience",
        "school": "School of Medicine",
        "base_url": "https://neuroscience.wustl.edu",
        "people_url": "https://neuroscience.wustl.edu/people/",
        "research_url": "https://neuroscience.wustl.edu/research/",
    },
    "biochem": {
        "name": "Biochemistry & Molecular Biophysics",
        "school": "School of Medicine",
        "base_url": "https://biochem.wustl.edu",
        "people_url": "https://biochem.wustl.edu/people/",
        "research_url": "https://biochem.wustl.edu/research/",
    },
    "cellbio": {
        "name": "Cell Biology & Physiology",
        "school": "School of Medicine",
        "base_url": "https://cellbiology.wustl.edu",
        "people_url": "https://cellbiology.wustl.edu/people/",
        "research_url": "https://cellbiology.wustl.edu/research/",
    },
    "devbio": {
        "name": "Developmental Biology",
        "school": "School of Medicine",
        "base_url": "https://devbio.wustl.edu",
        "people_url": "https://devbio.wustl.edu/people/",
        "research_url": "https://devbio.wustl.edu/research/",
    },
    "microbiology": {
        "name": "Molecular Microbiology",
        "school": "School of Medicine",
        "base_url": "https://microbiology.wustl.edu",
        "people_url": "https://microbiology.wustl.edu/people/",
        "research_url": "https://microbiology.wustl.edu/research/",
    },
    # ----------------------------------------------------------------
    # Clinical departments — add entries here to expand coverage:
    # "surgery":      {"name": "Surgery",      "base_url": "https://surgery.wustl.edu", ...},
    # "pediatrics":   {"name": "Pediatrics",   "base_url": "https://pediatrics.wustl.edu", ...},
    # "radiology":    {"name": "Radiology",    "base_url": "https://radiology.wustl.edu", ...},
    # ... etc for all 21 departments
    # ----------------------------------------------------------------
}


def get_faculty_and_areas(playwright: Playwright, dept_key: str) -> dict:
    """Scrape faculty and research areas for a med school department.

    Strategy:
    1. Visit /people/ page and extract faculty cards across all pages
    2. Visit /research/ page to discover research areas
    3. Map faculty to research areas where possible

    Returns: {area_name: {"faculty": [{"name": ..., "profile_url": ...}], "labs": []}}
    """
    config = MED_DEPTS[dept_key]
    base_url = config["base_url"]

    browser = playwright.chromium.launch()
    page = browser.new_page()

    # --- Step 1: Scrape all faculty from /people/ pages ---
    all_faculty = []
    people_url = config["people_url"]
    page_num = 1

    if safe_goto(page, people_url):
        # Wait for React-rendered faculty cards to appear
        try:
            page.wait_for_selector('.washu-ppi-card, .people-card, article', timeout=10000)
        except Exception:
            pass  # Continue even if timeout — page may have different structure

        all_faculty.extend(_extract_faculty_from_page(page, base_url))

        # Handle pagination: med school uses .nav-next a for page links
        page_num = 1
        while True:
            next_link = page.query_selector(
                '.nav-next a, '
                'a.next.page-numbers, '
                '.pagination a:has-text("Next"), '
                'a[rel="next"]'
            )
            if not next_link:
                break
            next_href = next_link.get_attribute("href")
            if not next_href:
                break
            next_url = next_href if next_href.startswith("http") else f"{base_url}{next_href}"
            if not safe_goto(page, next_url):
                break
            try:
                page.wait_for_selector('.washu-ppi-card, .people-card, article', timeout=10000)
            except Exception:
                pass
            new_faculty = _extract_faculty_from_page(page, base_url)
            if not new_faculty:
                break
            all_faculty.extend(new_faculty)
            page_num += 1
            time.sleep(1)

    # Deduplicate
    seen = set()
    unique_faculty = []
    for f in all_faculty:
        if f["name"] not in seen:
            seen.add(f["name"])
            unique_faculty.append(f)

    print(f"  Found {len(unique_faculty)} faculty across {page_num} page(s)")

    # --- Step 2: Scrape research areas from /research/ page ---
    research_areas = []
    research_url = config.get("research_url")

    # Skip words that indicate news/navigation, not research areas
    skip_area_words = {"next page", "previous page", "page", "load more", "nobel",
                       "ranks", "ranking", "seminar", "news", "events", "contact",
                       "home", "about", "menu", "search", "mitra lab", "lab"}

    if research_url and safe_goto(page, research_url):
        try:
            page.wait_for_selector('h2, h3, .washu-ppi-card', timeout=10000)
        except Exception:
            pass

        # Look for research area links in the main content area
        # Filter to links that point to research sub-pages
        area_links = page.query_selector_all(
            '.entry-content a[href*="/research/"], '
            'article a[href*="/research/"], '
            '.page-content a[href*="/research/"]'
        )
        for link in area_links:
            text = link.inner_text().strip()
            href = link.get_attribute("href") or ""
            text_lower = text.lower()
            if (text and len(text) > 3 and len(text) < 80
                    and not any(sw in text_lower for sw in skip_area_words)
                    and href.rstrip("/") != research_url.rstrip("/")):
                research_areas.append(text)

        # Also try PPI card elements (some research pages list areas as cards)
        if not research_areas:
            area_cards = page.query_selector_all('.washu-ppi-card h2, .washu-ppi-card h3')
            for card in area_cards:
                text = card.inner_text().strip()
                text_lower = text.lower()
                if (text and len(text) > 3 and len(text) < 80
                        and not any(sw in text_lower for sw in skip_area_words)):
                    research_areas.append(text)

        # Fallback: headings in the main content only
        if not research_areas:
            content = page.query_selector('.entry-content, article, .page-content, main')
            if content:
                for heading in content.query_selector_all("h2, h3"):
                    text = heading.inner_text().strip()
                    text_lower = text.lower()
                    if (text and len(text) > 3 and len(text) < 80
                            and not any(sw in text_lower for sw in skip_area_words)):
                        research_areas.append(text)

    # Deduplicate research areas
    research_areas = list(dict.fromkeys(research_areas))

    page.close()
    browser.close()

    # --- Step 3: Build result structure ---
    if research_areas:
        # Put all faculty under each area for now — med school sites don't always
        # map individual faculty to specific areas on the web
        results = {}
        for area in research_areas:
            results[area] = {
                "faculty": [],  # Will be populated if mapping is available
                "labs": [],
            }
        # Also add a "Department Faculty" catch-all with everyone
        results["Department Faculty"] = {
            "faculty": unique_faculty,
            "labs": [],
        }
        print(f"  Found {len(research_areas)} research areas")
    else:
        # No research areas found — all faculty under one group
        results = {
            "Department Faculty": {
                "faculty": unique_faculty,
                "labs": [],
            }
        }

    return results


def _extract_faculty_from_page(page, base_url: str) -> list[dict]:
    """Extract faculty from a WordPress card-based /people/ page.

    Med school sites use the washu-ppi (People Places Items) plugin which
    renders cards as React components. Faculty names are in nested spans
    inside h2.washu-ppi-name elements.
    """
    faculty = []

    # Try 1: WashU PPI card layout (most med school departments)
    ppi_cards = page.query_selector_all('div.washu-ppi-card.ppi-people-card')
    if ppi_cards:
        for card in ppi_cards:
            # Get profile URL from the card link
            link = card.query_selector('a.washu-ppi-card-link')
            if not link:
                link = card.query_selector('a.entry-title-link')
            if not link:
                continue

            href = link.get_attribute("href") or ""

            # Get name from h2.washu-ppi-name (text is in nested spans)
            name_el = card.query_selector('h2.washu-ppi-name')
            if name_el:
                name = name_el.inner_text().strip()
            else:
                name = link.inner_text().strip()

            if not name or len(name) < 3:
                continue

            if not href.startswith("http"):
                href = f"{base_url}{href}" if href.startswith("/") else f"{base_url}/{href}"

            faculty.append({"name": name, "profile_url": href})
        return faculty

    # Try 2: Generic WordPress card layouts
    person_links = page.query_selector_all(
        '.people-card a, '
        '.faculty-card a, '
        '.entry-title a, '
        'article a[href*="/faculty/"], '
        'article a[href*="/people/"], '
        '.card a[href*="/faculty/"], '
        '.card a[href*="/people/"]'
    )

    if not person_links:
        person_links = page.query_selector_all(
            'a[href*="/faculty/"], '
            'a[href*="/people/"]'
        )

    skip_names = {"faculty", "people", "staff", "back", "more", "view profile",
                  "home", "about", "research", "news", "contact"}

    seen = set()
    for link in person_links:
        href = link.get_attribute("href") or ""
        name = link.inner_text().strip()

        if not name or len(name) < 3 or len(name) > 100:
            continue
        if name.lower() in skip_names:
            continue
        if "/" in name:
            continue
        if href.rstrip("/").endswith(("/people", "/faculty")):
            continue

        if name in seen:
            continue
        seen.add(name)

        if not href.startswith("http"):
            href = f"{base_url}{href}" if href.startswith("/") else f"{base_url}/{href}"

        faculty.append({"name": name, "profile_url": href})

    return faculty


def scrape_med_faculty_profiles(data, dept_key: str):
    """Scrape med school faculty profile pages for research and bio info.

    WordPress faculty profiles typically have research descriptions and
    bio info under standard headings or in the main content area.
    """
    all_faculty = {}
    for area_info in data.values():
        for fac in area_info["faculty"]:
            name = fac["name"]
            if name not in all_faculty:
                all_faculty[name] = fac["profile_url"]

    print(f"\nScraping {len(all_faculty)} unique med faculty profiles...")

    profile_data = {}
    for name, url in all_faculty.items():
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Failed to fetch {name}: {e}")
            profile_data[name] = {"lab_website": None, "research": None, "research_interests": [], "bio": None}
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract research description
        research_text = None
        research_interests = []
        for heading in soup.find_all(["h2", "h3", "h4"]):
            heading_text = heading.get_text(strip=True).lower()
            if "research" in heading_text or "interest" in heading_text:
                parts = []
                for sib in heading.find_next_siblings():
                    if sib.name in ("h2", "h3", "h4"):
                        break
                    if sib.name in ("ul", "ol"):
                        for li in sib.find_all("li", recursive=False):
                            item_text = li.get_text(strip=True)
                            if item_text:
                                research_interests.append(item_text)
                    elif sib.name in ("p", "div"):
                        text = sib.get_text(strip=True)
                        if text and len(text) > 10:
                            parts.append(text)
                if parts:
                    research_text = " ".join(parts)
                break

        # Try the main content area if no heading-based research found
        if not research_text:
            content = soup.select_one(".entry-content, .page-content, article .content")
            if content:
                paragraphs = content.find_all("p")
                research_paras = []
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if text and len(text) > 50:
                        research_paras.append(text)
                if research_paras:
                    research_text = " ".join(research_paras[:3])

        # Extract biography
        bio_text = None
        for heading in soup.find_all(["h2", "h3", "h4"]):
            heading_text = heading.get_text(strip=True).lower()
            if any(kw in heading_text for kw in ("bio", "about", "background")):
                parts = []
                for sib in heading.find_next_siblings():
                    if sib.name in ("h2", "h3", "h4"):
                        break
                    if sib.name in ("p", "div"):
                        text = sib.get_text(strip=True)
                        if text and len(text) > 15:
                            parts.append(text)
                if parts:
                    bio_text = " ".join(parts)
                break

        # Extract lab website
        lab_website = None
        for a_tag in soup.find_all("a"):
            link_text = a_tag.get_text(strip=True).lower()
            if any(kw in link_text for kw in ("lab website", "research website", "lab site",
                                               "research site", "lab page", "lab home",
                                               "research group", "visit lab")):
                lab_website = a_tag.get("href")
                break

        profile_data[name] = {
            "lab_website": lab_website,
            "research": research_text,
            "research_interests": research_interests,
            "bio": bio_text,
        }

        print(f"  {name}: lab={'yes' if lab_website else 'no'}, research={'yes' if research_text else 'no'}, interests={len(research_interests)}, bio={'yes' if bio_text else 'no'}")
        time.sleep(REQUEST_DELAY)

    # Merge back
    for area_info in data.values():
        for fac in area_info["faculty"]:
            name = fac["name"]
            if name in profile_data:
                fac["lab_website"] = profile_data[name]["lab_website"]
                fac["research"] = profile_data[name]["research"]
                fac["research_interests"] = profile_data[name]["research_interests"]
                fac["bio"] = profile_data[name]["bio"]

    return data


def scrape_department(playwright: Playwright, dept_key: str,
                      skip_profiles=False, skip_labs=False, skip_enrichment=False) -> dict:
    """Full scraping pipeline for one med school department."""
    config = MED_DEPTS[dept_key]
    print(f"\n{'='*60}")
    print(f"Scraping: {config['name']} ({dept_key}) [School of Medicine]")
    print(f"{'='*60}")

    t0 = time.time()
    data = get_faculty_and_areas(playwright, dept_key)
    print(f"[Timing] Faculty & areas: {time.time() - t0:.1f}s")

    if not skip_profiles:
        t0 = time.time()
        data = scrape_med_faculty_profiles(data, dept_key)
        print(f"[Timing] Faculty profiles: {time.time() - t0:.1f}s")

    if not skip_labs:
        t0 = time.time()
        data = scrape_all_lab_websites(data)
        print(f"[Timing] Lab websites: {time.time() - t0:.1f}s")

    if not skip_enrichment:
        t0 = time.time()
        data = enrich_from_profiles_portal(data)
        print(f"[Timing] Profiles enrichment: {time.time() - t0:.1f}s")

    total_faculty = len({
        fac["name"]
        for area in data.values()
        for fac in area["faculty"]
    })
    print(f"\nTotal: {len(data)} research areas, {total_faculty} unique faculty")

    return {
        "department": config["name"],
        "department_key": dept_key,
        "school": config["school"],
        "base_url": config["base_url"],
        "research_areas": data,
    }
