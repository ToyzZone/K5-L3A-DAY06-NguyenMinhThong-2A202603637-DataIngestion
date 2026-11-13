"""Write the coherence audit sheet: the chunk covering 10 fixed source positions, for each chunking.

Positions depend only on the corpus (10 content pages evenly spaced in corpus order, middle character of
each), never on retrieval scores. `score_0_2` and `reason` are filled in by hand afterwards.

Run from starter/:  python -m scripts.coherence_samples
"""
import json

from src.ingestion import load_corpus
from src.run import INDEXES, ROOT, build_chunks

OUT = ROOT / "results" / "audit" / "coherence.json"

_, pages, _ = load_corpus()
rows = []
for position, page in enumerate(pages[len(pages) // 20::len(pages) // 10][:10], 1):
    offset = len(page.text) // 2
    for index in INDEXES:
        chunk = next(c for c in build_chunks(index, [page]) if c.metadata["char_end"] > offset)
        rows.append({"position": position, "source_id": page.document_id, "page": page.page, "char_offset": offset,
                     "anchor": page.text[offset - 30:offset + 30], "index": index, "chunk_id": chunk.chunk_id,
                     "chars": len(chunk.text), "text": chunk.text, "score_0_2": None, "reason": ""})

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("x", encoding="utf-8") as f:  # "x": refuse to overwrite hand-written labels
    json.dump(rows, f, ensure_ascii=False, indent=2)
print(f"{len(rows)} chunks to label ({len(rows) // len(INDEXES)} positions x {list(INDEXES)}) -> {OUT}")
