"""Ingest strategies A/B, then run A/B/C on one benchmark split and save top-3 traces.

Run from starter/:  python -m src.run dev      (choose the configuration here)
                    python -m src.run test     (once, after the configuration is fixed)
"""
import json
import os
import platform
import sys
import time
from datetime import datetime
from importlib.metadata import version
from statistics import mean, median, quantiles

import psycopg
from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import QUERY_PREFIX, MyEmbedder
from .evaluation import evaluate_query, has_evidence, summarize
from .ingestion import DATA_DIR, load_corpus
from .store import PgVectorStore

ROOT = DATA_DIR.parents[1]
TOP_K = 3
# One stored index per chunking. C searches B's index, so B and C differ only in the filter.
INDEXES = {
    "A": {"chunking": "fixed", "chunk_size": 500, "overlap": 50},
    # 800 = smallest round size at which >=90% of detected blocks fit whole in every document
    # (block p90: FM 781, HHS 616, WHO 711); fixed from chunk statistics before any retrieval run.
    "B": {"chunking": "paragraph", "chunk_size": 800, "overlap": 0},
}
CONFIGS = {"A": {"index": "A", "filter": False}, "B": {"index": "B", "filter": False},
           "C": {"index": "B", "filter": True}}


def build_chunks(index: str, pages: list) -> list:
    cfg = INDEXES[index]
    if cfg["chunking"] == "fixed":
        return [c for p in pages for c in fixed_size(p, cfg["chunk_size"], cfg["overlap"])]
    return [c for p in pages for c in by_paragraph(p, cfg["chunk_size"])]


def ingest(index: str, chunks: list, embedder: MyEmbedder, store: PgVectorStore) -> dict:
    texts = [c.text for c in chunks]
    started = time.perf_counter()
    vectors = embedder.embed_documents(texts)
    embedded = time.perf_counter()
    store.upsert(index, chunks, vectors)
    stored = time.perf_counter()
    first = store.count(index)
    store.upsert(index, chunks, vectors)  # same version again: the row count must not move
    if not first == store.count(index) == len(chunks):
        raise RuntimeError(f"index {index}: {len(chunks)} chunks but {first} rows, then {store.count(index)}")
    lengths, tokens = [len(t) for t in texts], embedder.token_counts(texts)
    return {**INDEXES[index], "chunks": len(chunks), "rows_after_reingest": store.count(index), "chars": sum(lengths),
            "length_min": min(lengths), "length_median": median(lengths), "length_mean": round(mean(lengths)),
            "length_p90": round(quantiles(lengths, n=10)[-1]), "length_max": max(lengths),
            "chunks_under_100_chars": sum(n < 100 for n in lengths), "tokens": sum(tokens),
            "chunks_truncated_by_model": sum(n > embedder.max_tokens for n in tokens),
            "embed_seconds": round(embedded - started, 1), "store_seconds": round(stored - embedded, 1),
            "cost_usd": 0}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("dev", "test"):
        sys.exit(__doc__)
    split = sys.argv[1]
    load_dotenv(DATA_DIR.parent / ".env")
    if not (url := os.getenv("DATABASE_URL")):
        sys.exit("DATABASE_URL missing: copy starter/.env.example to starter/.env first.")

    _, pages, _ = load_corpus()
    if len(pages) < 30:
        sys.exit(f"only {len(pages)} content pages, need >= 30")
    questions = [q for q in json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
                 if q["split"] == split]

    embedder = MyEmbedder()
    store = PgVectorStore(url, embedder.dimensions)
    store.create_schema()
    chunks = {index: build_chunks(index, pages) for index in INDEXES}
    indexes = {index: ingest(index, chunks[index], embedder, store) for index in INDEXES}

    out = ROOT / "results" / split
    out.mkdir(parents=True, exist_ok=True)
    query_vectors = {q["id"]: embedder.embed_query(q["question"]) for q in questions}
    traces = []
    for name, cfg in CONFIGS.items():
        mine = []
        for q in questions:
            filters = q.get("filter") if cfg["filter"] else None  # the scope named in the question, never the gold
            trace = evaluate_query(q, store.search(cfg["index"], query_vectors[q["id"]], TOP_K, filters))
            mine.append({"strategy": name, "filter_applied": filters,
                         # False = no single chunk holds the whole quote, so chunking (not ranking) lost it
                         "evidence_in_one_chunk": any(has_evidence(q, c.document_id, c.page, c.text)
                                                      for c in chunks[cfg["index"]]), **trace})
        (out / f"traces_{name}.json").write_text(json.dumps(mine, ensure_ascii=False, indent=2), encoding="utf-8")
        traces += mine

    with psycopg.connect(url) as conn:
        postgres, pgvector = conn.execute("SELECT current_setting('server_version'), extversion "
                                          "FROM pg_extension WHERE extname = 'vector'").fetchone()
    metrics = summarize(traces)
    for name, cfg in CONFIGS.items():
        mine = [t for t in traces if t["strategy"] == name]
        metrics[name][split]["evidence_in_one_chunk"] = sum(t["evidence_in_one_chunk"] for t in mine)
        metrics[name][split]["misses_at_3"] = [t["id"] for t in mine if not t["hit_at_3"]]
    summary = {
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"), "split": split,
        "questions": len(questions), "top_k": TOP_K, "content_pages": len(pages),
        "embedding": {"provider": "local sentence-transformers", "model": embedder.model_name,
                      "revision": embedder.revision, "dimensions": embedder.dimensions,
                      "max_tokens": embedder.max_tokens, "device": embedder.device,
                      "normalized": True, "query_prefix": QUERY_PREFIX, "document_prefix": ""},
        "store": {"engine": f"PostgreSQL {postgres} + pgvector {pgvector}", "table": "chunks",
                  "metric": "cosine (<=>)", "search": "exact sequential scan, no ANN index"},
        "versions": {"python": platform.python_version(),
                     **{p: version(p) for p in ("sentence-transformers", "torch", "psycopg", "pypdf")}},
        "configs": CONFIGS, "indexes": indexes, "metrics": metrics,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for index, s in indexes.items():
        print(f"index {index}: {s['chunks']} chunks, mean {s['length_mean']} chars, {s['tokens']} tokens, "
              f"{s['chunks_truncated_by_model']} truncated, embed {s['embed_seconds']}s, store {s['store_seconds']}s")
    for name in CONFIGS:
        m = metrics[name][split]
        print(f"{name} {split}: Hit@1 {m['hit_at_1']}/{m['n']}  Evidence Hit@3 {m['hit_at_3']}/{m['n']}  "
              f"filter-compliant {m['filter_compliant']}/{m['filter_questions']}  "
              f"evidence in one chunk {m['evidence_in_one_chunk']}/{m['n']}  misses@3 {m['misses_at_3']}")
    print(f"traces and summary -> {out}")


if __name__ == "__main__":
    main()
