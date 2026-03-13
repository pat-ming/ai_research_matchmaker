"""
PDF Research Paper Scraper
Extracts text (by section), tables, and figures from academic PDFs.
Uses PyMuPDF for text/font metadata + images, pdfplumber for tables.
Outputs: files.json and files.md in a named subdirectory.
"""

import sys
import os
import re
import json
from pathlib import Path
from collections import Counter

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
from io import BytesIO


# ── Nickname generation ──────────────────────────────────────────────────────

FILLER_WORDS = {
    "a", "an", "the", "of", "and", "for", "in", "with", "on", "to", "by",
    "from", "at", "is", "are", "was", "were", "its", "their", "this", "that",
}

# Known compound abbreviations (checked before individual word abbreviation)
COMPOUND_ABBREVIATIONS = {
    ("ordinary", "differential", "equations"): "ode",
    ("ordinary", "differential", "equation"): "ode",
    ("partial", "differential", "equations"): "pde",
    ("partial", "differential", "equation"): "pde",
    ("large", "language", "model"): "llm",
    ("large", "language", "models"): "llm",
    ("natural", "language", "processing"): "nlp",
    ("computer", "vision"): "cv",
    ("graph", "neural", "network"): "gnn",
    ("graph", "neural", "networks"): "gnn",
    ("long", "short", "term", "memory"): "lstm",
}

# Single-word abbreviation mappings
ABBREVIATIONS = {
    "neural": "neural",
    "network": "net",
    "networks": "nets",
    "learning": "learn",
    "reinforcement": "rl",
    "convolutional": "conv",
    "recurrent": "rnn",
    "generative": "gen",
    "adversarial": "adv",
    "attention": "attn",
    "transformer": "transformer",
    "representation": "repr",
    "optimization": "optim",
    "stochastic": "stoch",
    "variational": "var",
    "approximate": "approx",
    "inference": "infer",
    "classification": "cls",
    "recognition": "recog",
    "detection": "detect",
    "segmentation": "seg",
    "generation": "gen",
    "processing": "proc",
    "language": "lang",
    "machine": "machine",
    "deep": "deep",
}


def generate_nickname(title: str) -> str:
    """Generate a short snake_case nickname from a paper title."""
    words = re.findall(r"[a-zA-Z]+", title.lower())
    meaningful = [w for w in words if w not in FILLER_WORDS]

    if not meaningful:
        meaningful = words[:3]

    # First pass: replace known compound terms
    abbreviated = []
    i = 0
    while i < len(meaningful):
        matched = False
        # Try longest compounds first (4 words, then 3, then 2)
        for length in (4, 3, 2):
            if i + length <= len(meaningful):
                chunk = tuple(meaningful[i:i + length])
                if chunk in COMPOUND_ABBREVIATIONS:
                    abbreviated.append(COMPOUND_ABBREVIATIONS[chunk])
                    i += length
                    matched = True
                    break
        if not matched:
            abbreviated.append(ABBREVIATIONS.get(meaningful[i], meaningful[i]))
            i += 1

    # If result is short enough, use it directly; otherwise truncate
    nickname = "_".join(abbreviated)
    if len(nickname) > 30:
        nickname = "_".join(abbreviated[:3])

    return nickname


# ── Font analysis helpers ────────────────────────────────────────────────────

SECTION_PATTERNS = [
    r"^abstract$",
    r"^introduction$",
    r"^related\s+work",
    r"^background",
    r"^method(s|ology)?$",
    r"^approach$",
    r"^model$",
    r"^experiment(s|al)?",
    r"^result(s)?",
    r"^evaluation$",
    r"^discussion$",
    r"^conclusion(s)?$",
    r"^acknowledge?ment(s)?$",
    r"^references$",
    r"^appendix",
    r"^supplementary",
    r"^\d+(\.\d+)*\s+\w",  # numbered sections like "1 Introduction" or "2.1 Setup"
]


def is_bold(flags: int) -> bool:
    """Check if font flags indicate bold. Bit 4 (16) = bold in MuPDF."""
    return bool(flags & (1 << 4))


def analyze_font_sizes(doc: fitz.Document) -> dict:
    """Scan the document to find the dominant (body) font size."""
    size_counter = Counter()
    for page in doc:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for block in blocks:
            if block["type"] != 0:  # text blocks only
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if len(text) > 5:  # ignore tiny fragments
                        size_counter[round(span["size"], 1)] += len(text)

    if not size_counter:
        return {"body_size": 10.0}

    body_size = size_counter.most_common(1)[0][0]
    return {"body_size": body_size}


def looks_like_real_text(text: str) -> bool:
    """Check that text looks like actual words, not math symbols or garbage."""
    # Must contain at least some ASCII letters
    alpha_chars = sum(1 for c in text if c.isascii() and c.isalpha())
    if alpha_chars < 3:
        return False
    # Reject if mostly non-ASCII (math symbols, etc.)
    if alpha_chars / max(len(text.replace(" ", "")), 1) < 0.5:
        return False
    # Reject pure numbers / decimals like "0.1346"
    if re.match(r"^[\d\.\-\+\s]+$", text):
        return False
    return True


def is_header(text: str, font_size: float, font_flags: int, body_size: float) -> int:
    """
    Determine if text is a section header. Returns:
      0 = not a header
      1 = major section header
      2 = subsection header
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 200:
        return 0

    # Filter out math symbols, single characters, and gibberish
    if not looks_like_real_text(stripped):
        return 0

    size_diff = font_size - body_size

    # Check for known section name patterns
    clean = re.sub(r"^\d+(\.\d+)*\s*", "", stripped).strip()
    is_known_section = any(
        re.match(pat, stripped.lower()) or re.match(pat, clean.lower())
        for pat in SECTION_PATTERNS
    )

    # Numbered subsection like "2.1 Something"
    is_numbered_sub = bool(re.match(r"^\d+\.\d+\s+\w", stripped))

    # Major header: notably larger font or bold + known section name
    if size_diff >= 2.0 and len(stripped.split()) >= 2:
        return 1
    if size_diff >= 1.0 and (is_bold(font_flags) or is_known_section):
        return 1
    if is_bold(font_flags) and is_known_section and size_diff >= 0.0:
        return 1

    # Subsection: slightly larger or bold with numbered pattern
    if size_diff >= 0.8 and len(stripped.split()) >= 2:
        return 2
    if is_bold(font_flags) and is_numbered_sub:
        return 2
    if is_bold(font_flags) and size_diff >= 0.3 and 2 <= len(stripped.split()) <= 8:
        return 2

    return 0


# ── Text cleaning ────────────────────────────────────────────────────────────

# Regex for figure/table captions embedded in body text
_FIGURE_CAPTION_RE = re.compile(
    r"Figure\s+\d+[a-z]?\s*[:.].*?(?=\n[A-Z]|\n\n|\Z)", re.DOTALL
)
_TABLE_CAPTION_RE = re.compile(
    r"Table\s+\d+[a-z]?\s*[:.].*?(?=\n[A-Z]|\n\n|\Z)", re.DOTALL
)

# Unicode replacement character and common PDF garbage
_GARBAGE_RE = re.compile(r"[\ufffd\ufffe\uffff]")
# Runs of 2+ replacement characters / private-use / symbol chars
_GARBLED_RUN_RE = re.compile(r"[\ufffd\ufffe\uffff\u2580-\u259f\ue000-\uf8ff]{2,}")


def clean_text(text: str) -> str:
    """Clean up extracted PDF text."""
    # Remove runs of garbled unicode (custom font glyphs that didn't map)
    text = _GARBLED_RUN_RE.sub("", text)
    # Remove isolated replacement characters
    text = _GARBAGE_RE.sub("", text)

    # Remove figure/table captions from body text (they're in the figures already)
    text = _FIGURE_CAPTION_RE.sub("", text)
    text = _TABLE_CAPTION_RE.sub("", text)

    # Join lines that were broken mid-sentence by PDF column layout:
    # A line ending with a lowercase letter/comma followed by a line starting with lowercase
    # is a continuation, not a new paragraph.
    lines = text.split("\n")
    merged = []
    for line in lines:
        line = line.strip()
        if not line:
            merged.append("")
            continue
        if (merged
                and merged[-1]
                and not merged[-1].endswith((".", ":", ";", "!", "?"))
                and line[0].islower()):
            merged[-1] = merged[-1] + " " + line
        else:
            merged.append(line)

    text = "\n".join(merged)

    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace per line
    text = "\n".join(l.strip() for l in text.split("\n"))

    return text.strip()


# ── Text extraction ──────────────────────────────────────────────────────────

def extract_sections(pdf_path: str) -> tuple[str, list[dict]]:
    """Extract structured sections from a PDF using PyMuPDF."""
    doc = fitz.open(pdf_path)
    font_info = analyze_font_sizes(doc)
    body_size = font_info["body_size"]

    # Extract the paper title from the first page (largest font text)
    title = extract_title(doc)

    sections = []
    current_section = {"title": "Preamble", "level": 0, "content": "", "tables": [], "figures": []}

    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                line_text = ""
                line_size = 0.0
                line_flags = 0
                span_count = 0

                for span in line["spans"]:
                    line_text += span["text"]
                    line_size += span["size"]
                    line_flags |= span["flags"]
                    span_count += 1

                if span_count > 0:
                    line_size /= span_count

                line_text_stripped = line_text.strip()
                if not line_text_stripped:
                    continue

                header_level = is_header(line_text_stripped, line_size, line_flags, body_size)

                if header_level > 0:
                    # Save current section if it has content
                    if current_section["content"].strip():
                        sections.append(current_section)
                    current_section = {
                        "title": line_text_stripped,
                        "level": header_level,
                        "content": "",
                        "tables": [],
                        "figures": [],
                    }
                else:
                    current_section["content"] += line_text_stripped + "\n"

    # Don't forget the last section
    if current_section["content"].strip():
        sections.append(current_section)

    doc.close()

    # Clean all section content
    for section in sections:
        section["content"] = clean_text(section["content"])

    return title, sections


def extract_title(doc: fitz.Document) -> str:
    """Extract the paper title from the first page by finding the largest font text."""
    if len(doc) == 0:
        return "Unknown"

    page = doc[0]
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    max_size = 0
    title_parts = []

    # First pass: find the maximum font size on page 1
    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if span["size"] > max_size and len(span["text"].strip()) > 2:
                    max_size = span["size"]

    # Second pass: collect all text at that size (title may span multiple lines)
    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if abs(span["size"] - max_size) < 0.5 and span["text"].strip():
                    title_parts.append(span["text"].strip())

    return " ".join(title_parts) if title_parts else "Unknown"


# ── Table extraction ─────────────────────────────────────────────────────────

def extract_tables(pdf_path: str) -> dict[int, list]:
    """Extract tables from each page using pdfplumber. Returns {page_num: [tables]}."""
    tables_by_page = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_tables = page.extract_tables()
            if page_tables:
                tables_by_page[i] = page_tables
    return tables_by_page


def assign_tables_to_sections(sections: list[dict], tables_by_page: dict, doc: fitz.Document):
    """Assign extracted tables to the nearest preceding section."""
    if not tables_by_page:
        return

    # Build a rough mapping of which section covers which pages
    page_to_section_idx = {}
    current_page = 0
    for idx, section in enumerate(sections):
        # Count newlines as a rough proxy for page coverage
        lines = section["content"].count("\n")
        pages_covered = max(1, lines // 40)
        for p in range(current_page, current_page + pages_covered):
            page_to_section_idx[p] = idx
        current_page += pages_covered

    for page_num, tables in tables_by_page.items():
        # Find the closest section
        section_idx = page_to_section_idx.get(page_num, len(sections) - 1)
        section_idx = min(section_idx, len(sections) - 1)
        for table in tables:
            sections[section_idx]["tables"].append(table)


# ── Figure extraction ────────────────────────────────────────────────────────

# Minimum dimensions to consider an embedded image a real figure (not a LaTeX glyph)
MIN_FIGURE_WIDTH = 100
MIN_FIGURE_HEIGHT = 60


def _is_real_figure(doc: fitz.Document, xref: int) -> bool:
    """Filter out LaTeX equation/symbol images (small, grayscale, nearly black)."""
    try:
        base = doc.extract_image(xref)
        w, h = base.get("width", 0), base.get("height", 0)
        if w < MIN_FIGURE_WIDTH or h < MIN_FIGURE_HEIGHT:
            return False
        if base.get("cs-name") == "DeviceGray":
            img = Image.open(BytesIO(base["image"]))
            pixels = list(img.getdata())
            avg = sum(pixels) / len(pixels) if pixels else 0
            if avg < 5:
                return False
        return True
    except Exception:
        return False


def extract_figures(pdf_path: str, output_dir: Path) -> dict[int, list[str]]:
    """
    Extract figures by rendering the page region that contains them.
    This captures figures exactly as they appear in the PDF (layout, labels, axes, etc.).
    Filters out tiny LaTeX equation/symbol images.
    Returns {page_num: [filenames]}.
    """
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    figures_by_page = {}
    doc = fitz.open(pdf_path)

    for page_num, page in enumerate(doc):
        images = page.get_images(full=True)

        # Collect bounding rects of real figure images on this page
        figure_rects = []
        for img_info in images:
            xref = img_info[0]
            if not _is_real_figure(doc, xref):
                continue
            for rect in page.get_image_rects(xref):
                figure_rects.append(rect)

        if not figure_rects:
            continue

        # Compute bounding box encompassing all figure images on this page
        bbox = figure_rects[0]
        for rect in figure_rects[1:]:
            bbox = bbox | rect  # union of rects

        # Add a small margin to capture labels/captions near the figures
        margin = 15
        bbox = fitz.Rect(
            max(0, bbox.x0 - margin),
            max(0, bbox.y0 - margin),
            min(page.rect.width, bbox.x1 + margin),
            min(page.rect.height, bbox.y1 + margin),
        )

        # Render that region at 2x resolution for crisp output
        pixmap = page.get_pixmap(clip=bbox, dpi=200)
        filename = f"fig_p{page_num}.png"
        filepath = figures_dir / filename
        pixmap.save(filepath)

        figures_by_page[page_num] = [f"figures/{filename}"]

    doc.close()
    return figures_by_page


# ── Uncomment to also extract raw LaTeX equation images ──────────────────────
#
# def extract_equation_images(pdf_path: str, output_dir: Path):
#     """Extract small equation/symbol images that extract_figures skips."""
#     equations_dir = output_dir / "equations"
#     equations_dir.mkdir(parents=True, exist_ok=True)
#     doc = fitz.open(pdf_path)
#     for page_num, page in enumerate(doc):
#         for img_idx, img_info in enumerate(page.get_images(full=True)):
#             xref = img_info[0]
#             if _is_real_figure(doc, xref):
#                 continue
#             try:
#                 base = doc.extract_image(xref)
#                 ext = base.get("ext", "png")
#                 with open(equations_dir / f"eq_p{page_num}_{img_idx}.{ext}", "wb") as f:
#                     f.write(base["image"])
#             except Exception:
#                 continue
#     doc.close()


def assign_figures_to_sections(sections: list[dict], figures_by_page: dict):
    """Assign extracted figures to the nearest preceding section."""
    if not figures_by_page:
        return

    all_figures = []
    for page_num in sorted(figures_by_page.keys()):
        for fig_path in figures_by_page[page_num]:
            all_figures.append(fig_path)

    if not sections:
        return

    total_len = sum(len(s["content"]) for s in sections)
    if total_len == 0:
        sections[-1]["figures"] = all_figures
        return

    fig_idx = 0
    cumulative = 0
    for section in sections:
        cumulative += len(section["content"])
        cutoff = int(len(all_figures) * cumulative / total_len)
        while fig_idx < cutoff and fig_idx < len(all_figures):
            section["figures"].append(all_figures[fig_idx])
            fig_idx += 1

    while fig_idx < len(all_figures):
        sections[-1]["figures"].append(all_figures[fig_idx])
        fig_idx += 1


# ── Output writers ───────────────────────────────────────────────────────────

def save_json(title: str, sections: list[dict], output_path: Path):
    """Save text-only structured data as JSON (no tables/figures — those are separate files)."""
    text_sections = [
        {"title": s["title"], "level": s["level"], "content": s["content"]}
        for s in sections
    ]
    data = {
        "title": title,
        "sections": text_sections,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_markdown(title: str, sections: list[dict], output_path: Path):
    """Save structured data as Markdown."""
    lines = [f"# {title}\n"]

    for section in sections:
        level = section.get("level", 1)
        heading = "#" * (level + 1)  # ## for level 1, ### for level 2
        lines.append(f"\n{heading} {section['title']}\n")
        lines.append(section["content"].strip())

        # Tables
        for table_idx, table in enumerate(section.get("tables", [])):
            if not table:
                continue
            lines.append(f"\n**Table {table_idx + 1}:**\n")
            for row_idx, row in enumerate(table):
                cells = [str(c) if c else "" for c in row]
                lines.append("| " + " | ".join(cells) + " |")
                if row_idx == 0:
                    lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
            lines.append("")

        # Figures
        for fig in section.get("figures", []):
            lines.append(f"\n![Figure]({fig})\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── Main ─────────────────────────────────────────────────────────────────────

def scrape_pdf(pdf_path: str) -> Path:
    """Main entry point: scrape a PDF and save structured output."""
    pdf_path = os.path.abspath(pdf_path)
    if not os.path.isfile(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    pdf_dir = os.path.dirname(pdf_path)
    pdf_name = Path(pdf_path).stem

    # Generate nickname and create output directory
    nickname = generate_nickname(pdf_name)
    output_dir = Path(pdf_dir) / nickname
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scraping: {pdf_name}")
    print(f"Output directory: {output_dir}/")

    # Step 1: Extract sections
    print("  Extracting text and sections...")
    title, sections = extract_sections(pdf_path)
    print(f"    Found {len(sections)} sections")

    # Step 2: Extract tables
    print("  Extracting tables...")
    tables_by_page = extract_tables(pdf_path)
    total_tables = sum(len(t) for t in tables_by_page.values())
    print(f"    Found {total_tables} tables across {len(tables_by_page)} pages")
    doc = fitz.open(pdf_path)
    assign_tables_to_sections(sections, tables_by_page, doc)
    doc.close()

    # Step 3: Extract figures
    print("  Extracting figures...")
    figures_by_page = extract_figures(pdf_path, output_dir)
    total_figures = sum(len(f) for f in figures_by_page.values())
    print(f"    Found {total_figures} figures")
    assign_figures_to_sections(sections, figures_by_page)

    # Step 4: Save outputs
    json_path = output_dir / "files.json"
    md_path = output_dir / "files.md"
    save_json(title, sections, json_path)
    save_markdown(title, sections, md_path)

    print(f"\nSaved:")
    print(f"  {json_path}")
    print(f"  {md_path}")
    if total_figures > 0:
        print(f"  {output_dir / 'figures/'} ({total_figures} images)")

    # Print section summary
    print(f"\nSections:")
    for s in sections:
        indent = "  " if s["level"] <= 1 else "    "
        extras = []
        if s["tables"]:
            extras.append(f"{len(s['tables'])} table(s)")
        if s["figures"]:
            extras.append(f"{len(s['figures'])} figure(s)")
        extra_str = f" [{', '.join(extras)}]" if extras else ""
        print(f"{indent}- {s['title']}{extra_str}")

    return output_dir


if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_pdf = sys.argv[1]
    else:
        # Default to the test PDF in the same directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_pdf = os.path.join(script_dir, "Neural Ordinary Differential Equations.pdf")

    scrape_pdf(input_pdf)
