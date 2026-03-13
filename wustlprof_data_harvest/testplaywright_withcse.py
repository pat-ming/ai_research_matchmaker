from playwright.sync_api import sync_playwright, Playwright
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import time
import warnings

warnings.filterwarnings("ignore", message="Unverified HTTPS request")


def get_cse_research_areas(playwright: Playwright):
    browser = playwright.chromium.launch()
    page = browser.new_page()

    # Navigate to the CSE homepage
    page.goto("https://cse.washu.edu/index.html")

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
                area_urls.append(f"https://cse.washu.edu/{href.lstrip('/')}")

    results = {}

    for url in area_urls:
        page.goto(url)

        # Get the research area name from the page heading
        heading = page.query_selector("h2")
        area_name = heading.inner_text().strip() if heading else url.split("/")[-1].replace(".html", "").replace("-", " ")

        # Extract faculty names and profile URLs from links
        faculty_links = page.query_selector_all('a[href*="/faculty/"]')
        faculty = []
        seen_names = set()
        for fl in faculty_links:
            fname = fl.inner_text().strip()
            href = fl.get_attribute("href") or ""
            # Filter out nav/menu links — only keep actual name-like text
            if fname and len(fname) > 2 and "/" not in fname and fname not in seen_names:
                seen_names.add(fname)
                if not href.startswith("http"):
                    href = f"https://engineering.washu.edu{href}" if href.startswith("/") else f"https://engineering.washu.edu/{href}"
                faculty.append({"name": fname, "profile_url": href})

        # Extract labs — they appear under a <p class="module__title"> with text "Labs"
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

        print(f"Scraped: {area_name} — {len(faculty)} faculty, {len(labs)} labs")

    page.close()
    browser.close()

    return results


def scrape_faculty_profiles(data):
    """Use BeautifulSoup to scrape each faculty member's profile page
    for their lab/research website link and research description."""

    # Collect unique faculty across all research areas
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
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Failed to fetch {name}: {e}")
            profile_data[name] = {"lab_website": None, "research": None}
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find lab/research website link
        lab_website = None
        for a_tag in soup.find_all("a"):
            link_text = a_tag.get_text(strip=True).lower()
            if link_text in ("lab website", "research website", "lab site", "research site"):
                lab_website = a_tag.get("href")
                break

        # Find research description — under <p class="module__title">Research</p>
        research_text = None
        research_heading = soup.find("p", class_="module__title", string="Research")
        if research_heading:
            for sibling in research_heading.find_next_siblings():
                # Stop at the next section heading
                if sibling.name == "p" and "module__title" in (sibling.get("class") or []):
                    break
                if sibling.name in ("div", "p"):
                    text = sibling.get_text(strip=True)
                    if text:
                        research_text = text
                        break

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
            "bio": biography_text,
        }

        print(f"  {name}: lab_website={'yes' if lab_website else 'no'}, research={'yes' if research_text else 'no'}, bio={'yes' if biography_text else 'no'}")

    # Merge profile data back into the main results
    for area_info in data.values():
        for fac in area_info["faculty"]:
            name = fac["name"]
            if name in profile_data:
                fac["lab_website"] = profile_data[name]["lab_website"]
                fac["research"] = profile_data[name]["research"]
                fac["bio"] = profile_data[name]["bio"]

    return data


HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def scrape_lab_website(base_url):
    """Scrape a faculty lab/research website for research information.
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
        """Get only the direct text of an element, not nested children's text."""
        return "".join(
            child.strip() for child in element.strings
            if child.parent == element
        ).strip()

    def extract_research_content(soup):
        """Extract research-related headings and their associated text."""
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

        # Also grab paragraphs that start with a bold/strong topic label
        # (common pattern: "<p><b>Topic:</b> description...</p>")
        for p in soup.find_all("p"):
            bold = p.find(["b", "strong"])
            if bold:
                label = bold.get_text(strip=True).rstrip(":")
                full_text = p.get_text(strip=True)
                if label and len(full_text) > 50 and label not in [a for a in areas]:
                    # Only if it looks research-related (has substantial description)
                    if any(kw in label.lower() for kw in research_keywords) or len(full_text) > 100:
                        if label not in areas:
                            areas.append(label)
                        if full_text not in details:
                            details.append(full_text)

        return areas, details

    def extract_bio(soup):
        """Extract biography/about text from a page."""
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
        """Find navigation links that point to research-related pages."""
        research_urls = []
        seen = set()
        link_keywords = ["research", "project", "topic", "area"]

        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            text = a_tag.get_text(strip=True).lower()

            # Skip javascript/anchor/mailto links
            if href.startswith(("javascript:", "mailto:", "#")):
                continue

            if any(kw in text for kw in link_keywords) or any(kw in href.lower() for kw in link_keywords):
                full_url = urljoin(base, href)
                if full_url not in seen and full_url != base and full_url != base.rstrip("/"):
                    seen.add(full_url)
                    research_urls.append(full_url)

        return research_urls

    # Step 1: Fetch the homepage
    home_soup = fetch(base_url)
    if not home_soup:
        return {"research_areas": [], "research_details": [], "bio": None}

    # Step 2: Extract research content and bio from the homepage itself
    home_areas, home_details = extract_research_content(home_soup)
    all_areas.extend(home_areas)
    all_details.extend(home_details)
    bio_text = extract_bio(home_soup)

    # Step 3: Find research-related links on the homepage
    research_urls = find_research_links(home_soup, base_url)

    # Step 4: Follow each research link and extract content
    for url in research_urls[:3]:  # Limit to 3 subpages to avoid crawling too deep
        sub_soup = fetch(url)
        if sub_soup:
            body_text = sub_soup.get_text(strip=True)
            if len(body_text) > 100 and "not found" not in body_text.lower()[:200]:
                sub_areas, sub_details = extract_research_content(sub_soup)
                all_areas.extend(sub_areas)
                all_details.extend(sub_details)
                if not bio_text:
                    bio_text = extract_bio(sub_soup)

    # Deduplicate
    return {
        "research_areas": list(dict.fromkeys(all_areas)),
        "research_details": list(dict.fromkeys(all_details)),
        "bio": bio_text,
    }


def scrape_all_lab_websites(data):
    """Scrape each faculty member's lab/research website for detailed research info."""

    # Collect unique lab websites
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

    # Merge back into data
    for area_info in data.values():
        for fac in area_info["faculty"]:
            url = fac.get("lab_website")
            if url and url in lab_data:
                fac["lab_research_areas"] = lab_data[url]["research_areas"]
                fac["lab_research_details"] = lab_data[url]["research_details"]
                fac["lab_bio"] = lab_data[url]["bio"]

    return data


total_start = time.time()

t0 = time.time()
with sync_playwright() as playwright:
    data = get_cse_research_areas(playwright)
print(f"\n[Timing] Research areas: {time.time() - t0:.1f}s")

t0 = time.time()
data = scrape_faculty_profiles(data)
print(f"[Timing] Faculty profiles: {time.time() - t0:.1f}s")

t0 = time.time()
data = scrape_all_lab_websites(data)
print(f"[Timing] Lab websites: {time.time() - t0:.1f}s")

print("\n" + json.dumps(data, indent=2))

with open("cse_research_areas.json", "w") as f:
    json.dump(data, f, indent=2)
print(f"\nSaved to cse_research_areas.json")
print(f"[Timing] Total: {time.time() - total_start:.1f}s")
