"""
Scraper for McKelvey School of Engineering departments.

All 5 engineering departments share the same website template:
- research-areas/ pages with faculty and lab listings
- Faculty profiles on engineering.washu.edu
- Consistent CSS classes (module__title, etc.)

Departments: CSE, BME, ESE, EECE, MEMS
"""

from playwright.sync_api import Playwright
import time

from scraper_utils import (
    safe_goto,
    scrape_faculty_profiles,
    scrape_all_lab_websites,
    enrich_from_profiles_portal,
)

ENGINEERING_DEPTS = {
    "cse": {
        "name": "Computer Science & Engineering",
        "school": "McKelvey Engineering",
        "base_url": "https://cse.washu.edu",
        "homepage": "https://cse.washu.edu/index.html",
    },
    "bme": {
        "name": "Biomedical Engineering",
        "school": "McKelvey Engineering",
        "base_url": "https://bme.washu.edu",
        "homepage": "https://bme.washu.edu/index.html",
    },
    "ese": {
        "name": "Electrical & Systems Engineering",
        "school": "McKelvey Engineering",
        "base_url": "https://ese.washu.edu",
        "homepage": "https://ese.washu.edu/index.html",
    },
    "eece": {
        "name": "Energy, Environmental & Chemical Engineering",
        "school": "McKelvey Engineering",
        "base_url": "https://eece.washu.edu",
        "homepage": "https://eece.washu.edu/index.html",
    },
    "mems": {
        "name": "Mechanical Engineering & Materials Science",
        "school": "McKelvey Engineering",
        "base_url": "https://mems.washu.edu",
        "homepage": "https://mems.washu.edu/index.html",
    },
}


def get_research_areas(playwright: Playwright, dept_key: str) -> dict:
    """Scrape research areas, faculty, and labs for an engineering department.

    Navigates the department homepage, finds research-areas/ links,
    visits each, and extracts faculty and labs using the shared template
    selectors that work across all McKelvey departments.

    Returns: {area_name: {"faculty": [...], "labs": [...]}}
    """
    config = ENGINEERING_DEPTS[dept_key]
    base_url = config["base_url"]
    homepage = config["homepage"]

    browser = playwright.chromium.launch()
    page = browser.new_page()

    if not safe_goto(page, homepage):
        page.close()
        browser.close()
        return {}

    # Find all research area links from the nav menu
    research_links = page.query_selector_all('a[href*="research-areas/"]')
    area_urls = []
    seen = set()
    for link in research_links:
        href = link.get_attribute("href")
        if href and href not in seen:
            seen.add(href)
            if href.startswith("http"):
                area_urls.append(href)
            else:
                area_urls.append(f"{base_url}/{href.lstrip('/')}")

    results = {}

    for url in area_urls:
        if not safe_goto(page, url):
            continue

        # Get the research area name from the page heading
        # Some depts (e.g., BME) use generic h2 like "Primary Faculty" — fall back to URL
        url_name = url.split("/")[-1].replace(".html", "").replace("-", " ").title()
        generic_headings = {"primary faculty", "faculty", "affiliated faculty", "labs", "index", ""}
        area_name = url_name  # default from URL

        for h in page.query_selector_all("h1, h2"):
            text = h.inner_text().strip()
            if text and text.lower() not in generic_headings:
                area_name = text
                break

        # Extract faculty names and profile URLs
        faculty_links = page.query_selector_all('a[href*="/faculty/"]')
        faculty = []
        seen_names = set()
        for fl in faculty_links:
            fname = fl.inner_text().strip()
            href = fl.get_attribute("href") or ""
            # Skip generic link texts that match /faculty/ pattern (e.g., ESE "Learn more" links)
            generic_link_texts = {"learn more", "read more", "view profile", "view all",
                                  "see more", "more info", "details", "full profile"}
            if fname and len(fname) > 2 and "/" not in fname and fname.lower() not in generic_link_texts and fname not in seen_names:
                seen_names.add(fname)
                if not href.startswith("http"):
                    href = f"https://engineering.washu.edu{href}" if href.startswith("/") else f"https://engineering.washu.edu/{href}"
                faculty.append({"name": fname, "profile_url": href})

        # Extract labs — under <p class="module__title"> with text "Labs"
        labs = []
        lab_heading = page.query_selector('p.module__title:has-text("Labs")')
        if lab_heading:
            sibling = lab_heading.evaluate_handle("el => el.nextElementSibling").as_element()
            if sibling:
                lab_items = sibling.query_selector_all("li")
                for item in lab_items:
                    lab_name = item.inner_text().strip()
                    if lab_name:
                        labs.append(lab_name)

        results[area_name] = {
            "faculty": faculty,
            "labs": labs,
        }

        print(f"  Scraped: {area_name} — {len(faculty)} faculty, {len(labs)} labs")
        time.sleep(1)

    page.close()
    browser.close()

    return results


def scrape_department(playwright: Playwright, dept_key: str,
                      skip_profiles=False, skip_labs=False, skip_enrichment=False) -> dict:
    """Full scraping pipeline for one engineering department.

    Returns: {
        "department": str,
        "school": str,
        "base_url": str,
        "research_areas": {area_name: {"faculty": [...], "labs": [...]}},
    }
    """
    config = ENGINEERING_DEPTS[dept_key]
    print(f"\n{'='*60}")
    print(f"Scraping: {config['name']} ({dept_key.upper()})")
    print(f"{'='*60}")

    t0 = time.time()
    data = get_research_areas(playwright, dept_key)
    print(f"[Timing] Research areas: {time.time() - t0:.1f}s")

    if not skip_profiles:
        t0 = time.time()
        data = scrape_faculty_profiles(data)
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
