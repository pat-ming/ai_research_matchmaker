"""
Scraper for Arts & Sciences STEM departments.

A&S departments use a Drupal-based template (different from Engineering):
- Faculty listed on /people pages with area-of-interest filter checkboxes/dropdowns
- Profile URLs follow /people/first-last pattern
- Research interests in heading-based sections (h2/h3), not module__title classes
- Faculty listed as <article class="faculty-post"> with h3.name links
- Pagination via "Load More" buttons (Drupal pager)

Departments: Physics, Chemistry, Biology, Math, EEPS, IMSE, PNP, PBS
Note: IMSE uses the engineering template, not Drupal — handled with a flag.
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

ARTS_SCI_DEPTS = {
    "physics": {
        "name": "Physics",
        "school": "Arts & Sciences",
        "base_url": "https://physics.wustl.edu",
        "people_url": "https://physics.wustl.edu/people",
    },
    "chemistry": {
        "name": "Chemistry",
        "school": "Arts & Sciences",
        "base_url": "https://chemistry.wustl.edu",
        "people_url": "https://chemistry.wustl.edu/people",
    },
    "biology": {
        "name": "Biology",
        "school": "Arts & Sciences",
        "base_url": "https://biology.wustl.edu",
        "people_url": "https://biology.wustl.edu/people",
    },
    "math": {
        "name": "Mathematics & Statistics",
        "school": "Arts & Sciences",
        "base_url": "https://math.wustl.edu",
        "people_url": "https://math.wustl.edu/people",
    },
    "eeps": {
        "name": "Earth, Environmental & Planetary Sciences",
        "school": "Arts & Sciences",
        "base_url": "https://eeps.wustl.edu",
        "people_url": "https://eeps.wustl.edu/people",
    },
    "imse": {
        "name": "Institute of Materials Science & Engineering",
        "school": "Arts & Sciences",
        "base_url": "https://imse.washu.edu",
        "people_url": "https://imse.washu.edu/people/",
        "template": "engineering",
    },
    "pnp": {
        "name": "Philosophy-Neuroscience-Psychology",
        "school": "Arts & Sciences",
        "base_url": "https://pnp.wustl.edu",
        "people_url": "https://pnp.wustl.edu/people",
    },
    "pbs": {
        "name": "Psychological & Brain Sciences",
        "school": "Arts & Sciences",
        "base_url": "https://psych.wustl.edu",
        "people_url": "https://psych.wustl.edu/people",
    },
}


def get_faculty_and_areas(playwright: Playwright, dept_key: str) -> dict:
    """Scrape faculty and research areas for an Arts & Sciences department.

    Strategy:
    1. Visit /people page
    2. Extract area filters (checkboxes, select dropdowns, or links)
    3. For each area, apply filter and collect faculty names + profile URLs
    4. Handle pagination (both "Load More" and traditional next links)

    Returns: {area_name: {"faculty": [{"name": ..., "profile_url": ...}], "labs": []}}
    """
    config = ARTS_SCI_DEPTS[dept_key]
    base_url = config["base_url"]
    people_url = config["people_url"]
    template = config.get("template", "drupal")

    browser = playwright.chromium.launch()
    page = browser.new_page()

    if not safe_goto(page, people_url):
        page.close()
        browser.close()
        return {}

    # Step 1: Extract research area filters
    area_options = {}
    filter_type = None

    # Try 1: Checkbox filters (e.g., physics.wustl.edu uses these)
    checkbox_labels = page.query_selector_all(
        '#edit-areas .form-checkbox + label, '
        '[data-drupal-selector*="areas"] .form-checkbox + label, '
        '.bef-checkboxes label.option'
    )
    if checkbox_labels:
        filter_type = "checkbox"
        for label in checkbox_labels:
            text = label.inner_text().strip()
            for_attr = label.get_attribute("for")
            if for_attr:
                checkbox = page.query_selector(f"#{for_attr}")
                if checkbox:
                    value = checkbox.get_attribute("value")
                    if text and value:
                        area_options[text] = value

    # Try 2: Select dropdown
    if not area_options:
        select = page.query_selector(
            'select[name*="field_area"], select[name*="interest"], '
            'select[name*="cat"], select#edit-field-area-of-interest-tid'
        )
        if not select:
            selects = page.query_selector_all("select")
            for s in selects:
                opts = s.query_selector_all("option")
                if len(opts) > 2:
                    non_all = [o for o in opts if o.get_attribute("value") and o.get_attribute("value") != "All"]
                    if non_all:
                        select = s
                        break
        if select:
            filter_type = "select"
            for opt in select.query_selector_all("option"):
                value = opt.get_attribute("value")
                text = opt.inner_text().strip()
                if value and value not in ("All", "") and text:
                    area_options[text] = value

    # Try 3: Filter links (skip pagination links like "Load more")
    if not area_options:
        filter_links = page.query_selector_all('a[href*="?cat="], a[href*="field_area"], a[href*="interest"]')
        for link in filter_links:
            text = link.inner_text().strip()
            href = link.get_attribute("href") or ""
            if text and len(text) > 2 and text.lower() not in ("all", "show all", "reset", "load more"):
                filter_type = "link"
                area_options[text] = href

    results = {}

    if area_options:
        print(f"  Found {len(area_options)} research areas ({filter_type} filter)")

        for area_name, value in area_options.items():
            if filter_type == "checkbox":
                # Use URL-based filtering: navigate with the area parameter
                # This avoids issues with hidden submit buttons in Drupal
                # The checkbox name attribute tells us the URL param format
                target_cb = page.query_selector(f'input.form-checkbox[value="{value}"]')
                if target_cb:
                    cb_name = target_cb.get_attribute("name") or ""
                    # Build filter URL: e.g., /people?areas[449]=449
                    filter_url = f"{people_url}?{cb_name}={value}"
                    safe_goto(page, filter_url)
                    page.wait_for_load_state("networkidle", timeout=15000)

            elif filter_type == "select":
                # Use URL-based filtering instead of clicking submit (which may be hidden/timeout)
                select_name = select.get_attribute("name") or ""
                if select_name:
                    filter_url = f"{people_url}?{select_name}={value}"
                    safe_goto(page, filter_url)
                    page.wait_for_load_state("networkidle", timeout=15000)
                else:
                    # Fallback: interact with the select directly if name is missing
                    select.select_option(value=value)
                    page.wait_for_load_state("networkidle", timeout=15000)

            elif filter_type == "link":
                filter_url = value if value.startswith("http") else f"{base_url}{value}"
                safe_goto(page, filter_url)

            faculty = _extract_faculty_from_page(page, base_url, template)
            faculty = _paginate_and_collect(page, faculty, base_url, template)

            # Deduplicate
            seen = set()
            unique_faculty = []
            for f in faculty:
                if f["name"] not in seen:
                    seen.add(f["name"])
                    unique_faculty.append(f)

            results[area_name] = {
                "faculty": unique_faculty,
                "labs": [],
            }
            print(f"  Scraped: {area_name} — {len(unique_faculty)} faculty")
            time.sleep(1)
    else:
        # Fallback: no filter found — scrape all faculty under one group
        print("  No area filters found, scraping all faculty as one group")
        faculty = _extract_faculty_from_page(page, base_url, template)
        faculty = _paginate_and_collect(page, faculty, base_url, template)

        results["General"] = {
            "faculty": faculty,
            "labs": [],
        }
        print(f"  Scraped all faculty: {len(faculty)} total")

    page.close()
    browser.close()

    return results


def _paginate_and_collect(page, faculty: list, base_url: str, template: str) -> list:
    """Handle pagination — supports both 'Load More' buttons and next-page links."""
    max_pages = 20  # safety limit

    for _ in range(max_pages):
        # Try "Load More" button first (Drupal pager)
        load_more = page.query_selector('.pager--load-more a, a:has-text("Load more")')
        if load_more:
            try:
                load_more.click()
                page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(1)
                # Re-extract all faculty from the now-expanded page
                faculty = _extract_faculty_from_page(page, base_url, template)
                continue
            except Exception:
                break

        # Try traditional next link
        next_link = page.query_selector(
            'a[rel="next"], li.pager-next a, .pager__item--next a'
        )
        if not next_link:
            break
        next_href = next_link.get_attribute("href")
        if not next_href:
            break
        next_url = next_href if next_href.startswith("http") else f"{base_url}{next_href}"
        if not safe_goto(page, next_url):
            break
        faculty.extend(_extract_faculty_from_page(page, base_url, template))

    return faculty


def _extract_faculty_from_page(page, base_url: str, template: str = "drupal") -> list[dict]:
    """Extract faculty names and profile URLs from a /people listing page.

    Supports both Drupal (default A&S) and engineering templates.
    Drupal A&S sites use <article class="faculty-post"> with <h3 class="name"> links.
    """
    faculty = []

    if template == "engineering":
        person_links = page.query_selector_all(
            'a[href*="/faculty/"], '
            'a[href*="/people/"]'
        )
    else:
        # Drupal: try the specific faculty-post structure first
        person_links = page.query_selector_all(
            'article.faculty-post h3.name a, '
            'article.faculty-post h3 a[href*="/people/"]'
        )
        if not person_links:
            # Broader Drupal selectors
            person_links = page.query_selector_all(
                '.views-row a[href*="/people/"], '
                '.view-content a[href*="/people/"], '
                '.directory-listing a[href*="/people/"], '
                'a[href*="/people/"][class*="person"], '
                'a[href*="/people/"][class*="name"]'
            )
        if not person_links:
            person_links = page.query_selector_all('a[href*="/people/"]')

    skip_names = {"people", "faculty", "staff", "all", "back", "home", "about",
                  "research", "news", "events", "contact", "directory", "load more"}

    seen = set()
    for link in person_links:
        href = link.get_attribute("href") or ""
        name = link.inner_text().strip()
        # Clean up &nbsp; and whitespace artifacts
        name = name.replace("\xa0", " ")
        name = " ".join(name.split()).strip()

        if not name or len(name) < 3 or len(name) > 80:
            continue
        if "/" in name or name.lower() in skip_names:
            continue
        if href.rstrip("/").endswith(("/people", "/faculty")):
            continue

        if name in seen:
            continue
        seen.add(name)

        if not href.startswith("http"):
            if template == "engineering" and href.startswith("/"):
                href = f"https://engineering.washu.edu{href}"
            elif href.startswith("/"):
                href = f"{base_url}{href}"
            else:
                href = f"{base_url}/{href}"

        faculty.append({"name": name, "profile_url": href})

    return faculty


def scrape_as_faculty_profiles(data, dept_key: str):
    """Scrape A&S faculty profile pages for research and bio info.

    A&S profiles use Drupal template with heading-based sections
    (h2/h3) rather than p.module__title.
    """
    config = ARTS_SCI_DEPTS[dept_key]

    all_faculty = {}
    for area_info in data.values():
        for fac in area_info["faculty"]:
            name = fac["name"]
            if name not in all_faculty:
                all_faculty[name] = fac["profile_url"]

    print(f"\nScraping {len(all_faculty)} unique A&S faculty profiles...")

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

        # Extract research interests/description
        # Drupal uses both <h2>/<h3> AND <div class="heading"> for section labels.
        # Also use find_all_next() to traverse into nested div wrappers.
        research_text = None
        research_interests = []
        news_skip = {"news", "in the news", "undergraduate research", "graduate research"}

        # Build a combined list of heading-like elements
        heading_elements = soup.find_all(["h2", "h3", "h4"])
        heading_elements += soup.find_all("div", class_="heading")
        heading_elements += soup.find_all("div", class_="field-label")

        for heading in heading_elements:
            heading_text = heading.get_text(strip=True).lower().rstrip(":")
            # Match "research interests", "research", "areas of interest" etc.
            # but skip news headings that happen to contain "research"
            if heading_text in news_skip:
                continue
            if "research interest" in heading_text or heading_text in ("research", "research areas"):
                parts = []
                for sib in heading.find_next_siblings():
                    if sib.name in ("h2", "h3", "h4") or (sib.name == "div" and "heading" in (sib.get("class") or [])):
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
                if research_interests or research_text:
                    break

        # Extract biography
        # A&S Drupal profiles often have no "biography" heading — the main
        # descriptive paragraph sits between "mailing address" and "Professional History"
        bio_text = None
        for heading in soup.find_all(["h2", "h3", "h4"]):
            heading_text = heading.get_text(strip=True).lower()
            if any(kw in heading_text for kw in ("bio", "about", "overview")):
                parts = []
                for elem in heading.find_all_next():
                    if elem.name in ("h2", "h3", "h4") and elem != heading:
                        break
                    if elem.name == "p":
                        text = elem.get_text(strip=True)
                        if text and len(text) > 15:
                            parts.append(text)
                if parts:
                    bio_text = " ".join(parts)
                break

        # Fallback: extract main content paragraphs if no labeled sections found
        if not research_text and not bio_text:
            main_content = (soup.find("main") or soup.find("article")
                            or soup.find("div", class_=lambda c: c and "content" in c))
            if main_content:
                for p in main_content.find_all("p"):
                    text = p.get_text(strip=True)
                    if len(text) > 100:
                        text_lower = text.lower()[:80]
                        if not any(sk in text_lower for sk in ("mailing", "phone", "fax", "email")):
                            bio_text = text
                            break

        # Extract lab/research website — broaden matching for Drupal profiles
        # Link text varies: "Lab Website", "Research Group Website", "Herzog Lab", etc.
        lab_website = None
        lab_backup = None
        for a_tag in soup.find_all("a"):
            link_text = a_tag.get_text(strip=True).lower()
            href = a_tag.get("href", "")
            # Specific matches first
            if any(kw in link_text for kw in ("lab website", "research website", "lab site",
                                               "research site", "research group", "lab page",
                                               "laboratory website", "laboratory site")):
                lab_website = href
                break
            # Broader: any link with "lab" in text pointing to external URL
            if not lab_backup and "lab" in link_text and href.startswith("http"):
                lab_backup = href
        if not lab_website and lab_backup:
            lab_website = lab_backup

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
    """Full scraping pipeline for one A&S department."""
    config = ARTS_SCI_DEPTS[dept_key]
    print(f"\n{'='*60}")
    print(f"Scraping: {config['name']} ({dept_key}) [Arts & Sciences]")
    print(f"{'='*60}")

    t0 = time.time()
    data = get_faculty_and_areas(playwright, dept_key)
    print(f"[Timing] Faculty & areas: {time.time() - t0:.1f}s")

    if not skip_profiles:
        t0 = time.time()
        data = scrape_as_faculty_profiles(data, dept_key)
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
