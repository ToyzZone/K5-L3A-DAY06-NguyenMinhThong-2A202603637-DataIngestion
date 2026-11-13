"""Read and normalize source PDFs into traceable content pages."""
import json
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# ponytail: below this a page is blank/divider/figure-only; per-page review if a real page is that short
MIN_CHARS = 300
EDGE_LINES = 2  # running headers/footers live in the first/last 2 lines of a page
# Symbol/Wingdings bullets extracted as private-use or C1 code points (seen in this corpus) -> '•'; table icon dropped.
GLYPHS = str.maketrans({"": "•", "": "•", "": "•", "\x83": "•", "": None, "­": None})


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """One DocumentPage per physical page (1-based), raw text; empty pages kept so they can be logged."""
    reader = PdfReader(path)
    return [DocumentPage(document_id, source, i, page.extract_text() or "")
            for i, page in enumerate(reader.pages, 1)]


def normalize_text(text: str) -> str:
    """NFKC (ligatures, NBSP), font bullets -> '•', collapse spaces; keep line breaks for chunking."""
    text = unicodedata.normalize("NFKC", text).translate(GLYPHS)
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def strip_furniture(text: str, patterns: list[re.Pattern]) -> str:
    """Remove running headers/footers, only on the first/last EDGE_LINES lines of a page."""
    lines = text.split("\n")
    edge = set(range(EDGE_LINES)) | set(range(len(lines) - EDGE_LINES, len(lines)))
    out = []
    for i, line in enumerate(lines):
        if i in edge:
            for pattern in patterns:
                line = pattern.sub("", line).strip()
        if line:
            out.append(line)
    return "\n".join(out)


def load_corpus(config_path: Path = DATA_DIR / "sources.json") -> tuple[list[dict], list[DocumentPage], list[dict]]:
    """Return (sources, content pages with metadata, excluded pages with reason)."""
    sources = json.loads(config_path.read_text(encoding="utf-8"))
    pages, excluded = [], []
    for src in sources:
        section_of = {p: name for start, end, name in src["sections"] for p in range(start, end + 1)}
        patterns = [re.compile(p) for p in src["furniture"]]
        path = DATA_DIR / "pdf" / src["file"]
        for page in load_pdf(path, src["source_id"], f"data/pdf/{src['file']}"):
            text = strip_furniture(normalize_text(page.text), patterns)
            if page.page not in section_of:
                reason = "front/back matter (cover, contents, glossary, references, annex, index)"
            elif str(page.page) in src["exclude_pages"]:
                reason = src["exclude_pages"][str(page.page)]
            elif len(text) < MIN_CHARS:
                reason = f"<{MIN_CHARS} chars after normalization (blank, divider or figure-only)"
            else:
                page.text = text
                page.metadata = {"publisher": src["publisher"], "year": src["year"],
                                 "section": section_of[page.page]}
                pages.append(page)
                continue
            excluded.append({"source_id": src["source_id"], "page": page.page,
                             "chars": len(text), "reason": reason})
    return sources, pages, excluded
