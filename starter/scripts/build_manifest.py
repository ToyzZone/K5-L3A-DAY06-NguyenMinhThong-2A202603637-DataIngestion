"""Build data/manifest.json (repo root) from starter/data/sources.json + the PDFs.

Run from starter/:  python -m scripts.build_manifest
"""
import hashlib
import json
from collections import Counter

from src.ingestion import DATA_DIR, MIN_CHARS, load_corpus

OUT = DATA_DIR.parents[1] / "data" / "manifest.json"

sources, pages, excluded = load_corpus()
manifest = {"counting_rule": (
    "A content page = a physical PDF page (1-based) inside a listed content section, not a listed duplicate, "
    f"with >= {MIN_CHARS} characters after normalization and header/footer removal. Cover, contents, "
    "acknowledgements, glossary, references, annexes and index are outside the sections and not counted."),
    "sources": []}

for src in sources:
    sid = src["source_id"]
    mine = [p for p in pages if p.document_id == sid]
    skipped = [e for e in excluded if e["source_id"] == sid]
    pdf = DATA_DIR / "pdf" / src["file"]
    manifest["sources"].append({
        **{k: src[k] for k in ("source_id", "title", "publisher", "year", "version", "license_or_permission", "accessed_at")},
        "source_path_or_url": {"local": f"starter/data/pdf/{src['file']}", "url": src["url"]},
        "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "physical_pages": len(mine) + len(skipped),
        "content_pages": len(mine),
        "content_chars": sum(len(p.text) for p in mine),
        "pages": [{"page": p.page, "section": p.metadata["section"], "chars": len(p.text)} for p in mine],
        "excluded_pages": [{k: e[k] for k in ("page", "chars", "reason")} for e in skipped],
    })

# Smoke checks: enough pages, and running headers really stripped from the page edges.
assert len(pages) >= 30, f"only {len(pages)} content pages"
assert not any(p.text.startswith(("1 October 2020 FM 7-22", "Chapter 4. Active Adults")) for p in pages)

OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
for s in manifest["sources"]:
    reasons = Counter(e["reason"].split(" (")[0] for e in s["excluded_pages"])
    print(f"{s['source_id']:14s} physical={s['physical_pages']:3d} content={s['content_pages']:3d} "
          f"chars={s['content_chars']:,} excluded={dict(reasons)}")
print(f"TOTAL content pages = {len(pages)} -> {OUT}")
