"""
Shared utilities for WashU STEM scrapers.
Contains reusable functions for faculty profile scraping, lab website scraping,
and common helpers used across all three school scrapers.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import warnings

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

REQUEST_DELAY = 0.1  # seconds between HTTP requests (servers naturally take ~0.4s)


def safe_goto(page, url, retries=2, timeout=30000):
    """Navigate a Playwright page to a URL with retry + backoff."""
    for attempt in range(retries + 1):
        try:
            page.goto(url, timeout=timeout)
            return True
        except Exception as e:
            if attempt < retries:
                wait = 2 ** attempt
                print(f"  Retry {attempt + 1} for {url} (waiting {wait}s)...")
                time.sleep(wait)
            else:
                print(f"  Failed to load {url}: {e}")
                return False


def scrape_faculty_profiles(data):
    """Scrape engineering faculty profile pages on engineering.washu.edu.

    Extracts lab/research website link, research description, and biography
    from each faculty member's profile page using BeautifulSoup.

    Works for all McKelvey Engineering departments since all profiles live
    on engineering.washu.edu with identical HTML structure.
    """
    all_faculty = {}
    for area_info in data.values():
        for fac in area_info["faculty"]:
            name = fac["name"]
            if name not in all_faculty:
                all_faculty[name] = fac["profile_url"]

    print(f"\nScraping {len(all_faculty)} unique faculty profiles...")

    profile_data = {}
    for name, url in all_faculty.items():
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Failed to fetch {name}: {e}")
            profile_data[name] = {"lab_website": None, "research": None, "bio": None}
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find lab/research website link
        lab_website = None
        for a_tag in soup.find_all("a"):
            link_text = a_tag.get_text(strip=True).lower()
            if link_text in ("lab website", "research website", "lab site", "research site"):
                lab_website = a_tag.get("href")
                break

        # Find research interests — under <p class="module__title"> with
        # text "Research", "Research Interests", etc. Collect ALL content
        # (paragraphs, lists, divs) until the next section heading.
        research_text = None
        research_interests = []

        research_heading = None
        for p in soup.find_all("p", class_="module__title"):
            p_text = p.get_text(strip=True).lower()
            if p_text in ("research", "research interests", "research interest",
                          "research areas", "areas of interest"):
                research_heading = p
                break

        if research_heading:
            research_parts = []
            for sibling in research_heading.find_next_siblings():
                if sibling.name == "p" and "module__title" in (sibling.get("class") or []):
                    break
                if sibling.name in ("ul", "ol"):
                    for li in sibling.find_all("li", recursive=False):
                        item_text = li.get_text(strip=True)
                        if item_text:
                            research_interests.append(item_text)
                elif sibling.name in ("div", "p"):
                    text = sibling.get_text(strip=True)
                    if text:
                        research_parts.append(text)
            if research_parts:
                research_text = " ".join(research_parts)

        # Find biography — under <p class="module__title">Biography</p>
        biography_text = None
        bio_heading = soup.find("p", class_="module__title", string="Biography")
        if bio_heading:
            bio_parts = []
            for sibling in bio_heading.find_next_siblings():
                if sibling.name == "p" and "module__title" in (sibling.get("class") or []):
                    break
                if sibling.name in ("div", "p"):
                    text = sibling.get_text(strip=True)
                    if text:
                        bio_parts.append(text)
            if bio_parts:
                biography_text = " ".join(bio_parts)

        profile_data[name] = {
            "lab_website": lab_website,
            "research": research_text,
            "research_interests": research_interests,
            "bio": biography_text,
        }

        print(f"  {name}: lab={'yes' if lab_website else 'no'}, research={'yes' if research_text else 'no'}, interests={len(research_interests)}, bio={'yes' if biography_text else 'no'}")
        time.sleep(REQUEST_DELAY)

    # Merge profile data back into the main results
    for area_info in data.values():
        for fac in area_info["faculty"]:
            name = fac["name"]
            if name in profile_data:
                fac["lab_website"] = profile_data[name]["lab_website"]
                fac["research"] = profile_data[name]["research"]
                fac["research_interests"] = profile_data[name]["research_interests"]
                fac["bio"] = profile_data[name]["bio"]

    return data


def scrape_lab_website(base_url):
    """Scrape a faculty lab/research website for research information.
    Works with any lab URL — completely generic.

    1. Fetch homepage, find research nav links, and extract homepage content.
    2. Follow discovered research links and extract content from those pages.
    """
    all_areas = []
    all_details = []

    def fetch(url):
        try:
            resp = requests.get(url, timeout=10, verify=False, headers=HEADERS)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException:
            pass
        return None

    def get_direct_text(element):
        return "".join(
            child.strip() for child in element.strings
            if child.parent == element
        ).strip()

    def extract_research_content(soup):
        areas = []
        details = []
        skip_keywords = ["teach", "course", "fish", "hobby", "contact", "address",
                         "phone", "enjoy", "modified", "last updated", "copyright"]
        research_keywords = ["research", "project", "area", "topic", "interest"]

        for heading_tag in ["h1", "h2", "h3", "h4"]:
            for heading in soup.find_all(heading_tag):
                heading_text = heading.get_text(strip=True)
                if not heading_text:
                    continue
                heading_lower = heading_text.lower()
                if any(kw in heading_lower for kw in research_keywords):
                    content_parts = []
                    for sib in heading.find_next_siblings():
                        if sib.name == heading_tag:
                            break
                        if sib.name in ("ul", "ol"):
                            for li in sib.find_all("li", recursive=False):
                                direct = get_direct_text(li)
                                if not direct:
                                    first_link = li.find("a")
                                    direct = first_link.get_text(strip=True) if first_link else li.get_text(strip=True)
                                if direct and len(direct) > 3:
                                    areas.append(direct)
                        elif sib.name in ("h3", "h4", "h5"):
                            sub = sib.get_text(strip=True)
                            if sub and len(sub) > 3:
                                areas.append(sub)
                        elif sib.name in ("p", "div"):
                            text = sib.get_text(strip=True)
                            if text and len(text) > 30:
                                if not any(sk in text.lower()[:80] for sk in skip_keywords):
                                    content_parts.append(text)
                    if content_parts:
                        details.extend(content_parts)

        for p in soup.find_all("p"):
            bold = p.find(["b", "strong"])
            if bold:
                label = bold.get_text(strip=True).rstrip(":")
                full_text = p.get_text(strip=True)
                if label and len(full_text) > 50 and label not in [a for a in areas]:
                    if any(kw in label.lower() for kw in research_keywords) or len(full_text) > 100:
                        if label not in areas:
                            areas.append(label)
                        if full_text not in details:
                            details.append(full_text)

        return areas, details

    def extract_bio(soup):
        bio_keywords = ["about", "bio", "biography", "people", "overview"]
        for heading_tag in ["h1", "h2", "h3", "h4"]:
            for heading in soup.find_all(heading_tag):
                heading_text = heading.get_text(strip=True)
                if not heading_text:
                    continue
                if any(kw in heading_text.lower() for kw in bio_keywords):
                    bio_parts = []
                    for sib in heading.find_next_siblings():
                        if sib.name == heading_tag:
                            break
                        if sib.name in ("p", "div"):
                            text = sib.get_text(strip=True)
                            if text and len(text) > 20:
                                bio_parts.append(text)
                    if bio_parts:
                        return " ".join(bio_parts)
        return None

    def find_research_links(soup, base):
        research_urls = []
        seen = set()
        link_keywords = ["research", "project", "topic", "area"]
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            text = a_tag.get_text(strip=True).lower()
            if href.startswith(("javascript:", "mailto:", "#")):
                continue
            if any(kw in text for kw in link_keywords) or any(kw in href.lower() for kw in link_keywords):
                full_url = urljoin(base, href)
                if full_url not in seen and full_url != base and full_url != base.rstrip("/"):
                    seen.add(full_url)
                    research_urls.append(full_url)
        return research_urls

    home_soup = fetch(base_url)
    if not home_soup:
        return {"research_areas": [], "research_details": [], "bio": None}

    home_areas, home_details = extract_research_content(home_soup)
    all_areas.extend(home_areas)
    all_details.extend(home_details)
    bio_text = extract_bio(home_soup)

    research_urls = find_research_links(home_soup, base_url)

    for url in research_urls[:3]:
        sub_soup = fetch(url)
        if sub_soup:
            body_text = sub_soup.get_text(strip=True)
            if len(body_text) > 100 and "not found" not in body_text.lower()[:200]:
                sub_areas, sub_details = extract_research_content(sub_soup)
                all_areas.extend(sub_areas)
                all_details.extend(sub_details)
                if not bio_text:
                    bio_text = extract_bio(sub_soup)

    return {
        "research_areas": list(dict.fromkeys(all_areas)),
        "research_details": list(dict.fromkeys(all_details)),
        "bio": bio_text,
    }


def scrape_all_lab_websites(data):
    """Scrape each faculty member's lab/research website for detailed research info.
    Works with any data dict that has the standard faculty structure.
    """
    all_labs = {}
    for area_info in data.values():
        for fac in area_info["faculty"]:
            url = fac.get("lab_website")
            if url and url not in all_labs:
                all_labs[url] = fac["name"]

    print(f"\nScraping {len(all_labs)} unique lab/research websites...")

    lab_data = {}
    for url, name in all_labs.items():
        info = scrape_lab_website(url)
        lab_data[url] = info
        n_areas = len(info["research_areas"])
        n_details = len(info["research_details"])
        print(f"  {name}: {n_areas} areas, {n_details} detail sections, bio={'yes' if info['bio'] else 'no'}")
        time.sleep(REQUEST_DELAY)

    for area_info in data.values():
        for fac in area_info["faculty"]:
            url = fac.get("lab_website")
            if url and url in lab_data:
                fac["lab_research_areas"] = lab_data[url]["research_areas"]
                fac["lab_research_details"] = lab_data[url]["research_details"]
                fac["lab_bio"] = lab_data[url]["bio"]

    return data


def enrich_from_profiles_portal(data):
    """Enrich faculty data with info from profiles.wustl.edu (supplementary).

    Searches for each faculty member and extracts publication counts,
    research keywords, and collaboration info. Best-effort — failures
    don't affect primary data.
    """
    all_faculty = {}
    for area_info in data.values():
        for fac in area_info["faculty"]:
            name = fac["name"]
            if name not in all_faculty:
                all_faculty[name] = fac

    print(f"\nEnriching {len(all_faculty)} faculty from profiles.wustl.edu...")

    for name, fac in all_faculty.items():
        try:
            search_url = f"https://profiles.wustl.edu/en/searchAll/index/?search={requests.utils.quote(name)}&pageSize=5&showAdvanced=false&allConcepts=false&inferConcepts=false&searchBy=PartOfNameOrTitle"
            resp = requests.get(search_url, timeout=10, headers=HEADERS)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for the first result link that matches the name
            result_link = None
            for a_tag in soup.select("a.link.person"):
                link_name = a_tag.get_text(strip=True).lower()
                # Check if most of the name words appear in the result
                name_parts = name.lower().split()
                if sum(1 for p in name_parts if p in link_name) >= len(name_parts) - 1:
                    result_link = a_tag.get("href")
                    break

            if not result_link:
                continue

            if not result_link.startswith("http"):
                result_link = f"https://profiles.wustl.edu{result_link}"

            # Fetch the profile page
            prof_resp = requests.get(result_link, timeout=10, headers=HEADERS)
            if prof_resp.status_code != 200:
                continue

            prof_soup = BeautifulSoup(prof_resp.text, "html.parser")

            # Extract research keywords/fingerprints
            keywords = []
            for kw_el in prof_soup.select(".concept-badge, .keyword-group .keyword"):
                kw = kw_el.get_text(strip=True)
                if kw and len(kw) > 2:
                    keywords.append(kw)

            if keywords:
                fac["profile_keywords"] = keywords[:20]

            # Extract publication count if visible
            pub_count_el = prof_soup.select_one(".portal-count, .result-count")
            if pub_count_el:
                count_text = pub_count_el.get_text(strip=True)
                digits = "".join(c for c in count_text if c.isdigit())
                if digits:
                    fac["publication_count"] = int(digits)

            fac["profiles_url"] = result_link
            print(f"  {name}: keywords={len(keywords)}, url={result_link}")

        except Exception as e:
            print(f"  {name}: enrichment failed ({e})")

        time.sleep(REQUEST_DELAY)

    return data
