"""
WashU STEM Department Scraper — Main Entry Point

General-purpose scraper for all WashU STEM departments across three schools:
- McKelvey Engineering (5 depts): CSE, BME, ESE, EECE, MEMS
- Arts & Sciences (4 depts): Physics, Chemistry, Biology, Math
- School of Medicine (6 basic science depts, extensible to all 21)

Usage:
    python washu_stem_scraper.py --list                    # show all departments
    python washu_stem_scraper.py cse                       # single department
    python washu_stem_scraper.py engineering                # all engineering
    python washu_stem_scraper.py as                         # all arts & sciences
    python washu_stem_scraper.py med                        # all medicine
    python washu_stem_scraper.py all                        # everything
    python washu_stem_scraper.py cse bme physics genetics   # mix and match
    python washu_stem_scraper.py engineering --skip-labs    # skip slow lab scraping
    python washu_stem_scraper.py all --skip-enrichment     # skip profiles.wustl.edu
"""

from playwright.sync_api import sync_playwright
import argparse
import json
import time
from datetime import datetime

from scraper_engineering import ENGINEERING_DEPTS, scrape_department as scrape_eng
from scraper_artssci import ARTS_SCI_DEPTS, scrape_department as scrape_as
from scraper_med import MED_DEPTS, scrape_department as scrape_med

ALL_DEPTS = {**ENGINEERING_DEPTS, **ARTS_SCI_DEPTS, **MED_DEPTS}

# Shorthand groups for CLI
GROUPS = {
    "engineering": list(ENGINEERING_DEPTS.keys()),
    "eng": list(ENGINEERING_DEPTS.keys()),
    "as": list(ARTS_SCI_DEPTS.keys()),
    "artssci": list(ARTS_SCI_DEPTS.keys()),
    "med": list(MED_DEPTS.keys()),
    "medicine": list(MED_DEPTS.keys()),
    "all": list(ALL_DEPTS.keys()),
}


def resolve_departments(args: list[str]) -> list[str]:
    """Resolve CLI args into a flat list of department keys."""
    if not args:
        return list(ALL_DEPTS.keys())

    dept_keys = []
    for arg in args:
        arg_lower = arg.lower()
        if arg_lower in GROUPS:
            dept_keys.extend(GROUPS[arg_lower])
        elif arg_lower in ALL_DEPTS:
            dept_keys.append(arg_lower)
        else:
            print(f"Warning: Unknown department or group '{arg}', skipping.")

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for k in dept_keys:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique


def print_department_list():
    """Print all available departments grouped by school."""
    print("\nAvailable departments:\n")

    print("  McKelvey Engineering (group: 'engineering')")
    for key, config in ENGINEERING_DEPTS.items():
        print(f"    {key:15s}  {config['name']}")

    print(f"\n  Arts & Sciences (group: 'as')")
    for key, config in ARTS_SCI_DEPTS.items():
        print(f"    {key:15s}  {config['name']}")

    print(f"\n  School of Medicine (group: 'med')")
    for key, config in MED_DEPTS.items():
        print(f"    {key:15s}  {config['name']}")

    print(f"\n  Use 'all' to scrape everything ({len(ALL_DEPTS)} departments)")
    print()


def scrape_department(playwright, dept_key: str, skip_profiles=False,
                      skip_labs=False, skip_enrichment=False) -> dict:
    """Dispatch to the correct school-specific scraper."""
    if dept_key in ENGINEERING_DEPTS:
        return scrape_eng(playwright, dept_key, skip_profiles, skip_labs, skip_enrichment)
    elif dept_key in ARTS_SCI_DEPTS:
        return scrape_as(playwright, dept_key, skip_profiles, skip_labs, skip_enrichment)
    elif dept_key in MED_DEPTS:
        return scrape_med(playwright, dept_key, skip_profiles, skip_labs, skip_enrichment)
    else:
        print(f"Error: Unknown department '{dept_key}'")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="WashU STEM Department Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Groups:
  engineering / eng    All 5 McKelvey Engineering departments
  as / artssci         All 4 Arts & Sciences STEM departments
  med / medicine       All 6 School of Medicine basic science departments
  all                  All departments

Examples:
  %(prog)s cse bme physics    Scrape specific departments
  %(prog)s engineering        All engineering departments
  %(prog)s all --skip-labs    Everything, but skip lab website scraping
        """
    )
    parser.add_argument(
        "departments",
        nargs="*",
        default=None,
        help="Department keys or groups to scrape (default: all)",
    )
    parser.add_argument(
        "-o", "--output",
        default="washu_stem_data.json",
        help="Output JSON file path (default: washu_stem_data.json)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available department keys and exit",
    )
    parser.add_argument(
        "--skip-profiles",
        action="store_true",
        help="Skip faculty profile scraping (faster)",
    )
    parser.add_argument(
        "--skip-labs",
        action="store_true",
        help="Skip lab website scraping (faster)",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip profiles.wustl.edu enrichment (faster)",
    )

    args = parser.parse_args()

    if args.list:
        print_department_list()
        return

    dept_keys = resolve_departments(args.departments)
    if not dept_keys:
        print("No valid departments specified. Use --list to see available options.")
        return

    print(f"\nWashU STEM Scraper")
    print(f"Departments to scrape: {', '.join(dept_keys)}")
    print(f"Output: {args.output}")
    if args.skip_profiles:
        print("Skipping: faculty profile scraping")
    if args.skip_labs:
        print("Skipping: lab website scraping")
    if args.skip_enrichment:
        print("Skipping: profiles.wustl.edu enrichment")

    total_start = time.time()
    results = {}
    failed = []

    with sync_playwright() as playwright:
        for dept_key in dept_keys:
            try:
                dept_data = scrape_department(
                    playwright,
                    dept_key,
                    skip_profiles=args.skip_profiles,
                    skip_labs=args.skip_labs,
                    skip_enrichment=args.skip_enrichment,
                )
                if dept_data:
                    results[dept_key] = dept_data

                    # Partial save after each department
                    _save_output(results, args.output, dept_keys)

            except Exception as e:
                print(f"\nERROR scraping {dept_key}: {e}")
                failed.append(dept_key)

    # Final save
    _save_output(results, args.output, dept_keys)

    # Summary
    total_time = time.time() - total_start
    total_faculty = 0
    total_areas = 0
    for dept in results.values():
        areas = dept.get("research_areas", {})
        total_areas += len(areas)
        total_faculty += len({
            fac["name"]
            for area in areas.values()
            for fac in area["faculty"]
        })

    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETE")
    print(f"{'='*60}")
    print(f"Departments scraped: {len(results)}/{len(dept_keys)}")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print(f"Total research areas: {total_areas}")
    print(f"Total unique faculty: {total_faculty}")
    print(f"Output saved to: {args.output}")
    print(f"Total time: {total_time:.1f}s")


def _save_output(results: dict, output_path: str, dept_keys: list[str]):
    """Save current results to JSON with metadata."""
    total_faculty = 0
    for dept in results.values():
        total_faculty += len({
            fac["name"]
            for area in dept.get("research_areas", {}).values()
            for fac in area["faculty"]
        })

    output = {
        "metadata": {
            "scrape_timestamp": datetime.now().isoformat(),
            "departments_requested": dept_keys,
            "departments_scraped": list(results.keys()),
            "total_faculty": total_faculty,
            "total_research_areas": sum(
                len(d.get("research_areas", {})) for d in results.values()
            ),
        },
        "departments": results,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)


if __name__ == "__main__":
    main()
