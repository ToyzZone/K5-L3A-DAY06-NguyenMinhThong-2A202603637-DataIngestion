"""Check benchmark/questions.json against the normalized corpus; exit 1 on any error.

Run from starter/:  python -m scripts.verify_benchmark [path/to/questions.json]
"""
import json
import sys
from collections import Counter
from pathlib import Path

from src.evaluation import golds, squash
from src.ingestion import DATA_DIR, load_corpus

PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR.parents[1] / "benchmark" / "questions.json"
REQUIRED = ("id", "split", "type", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote")


_, pages, _ = load_corpus()
text = {(p.document_id, p.page): squash(p.text) for p in pages}
meta = {(p.document_id, p.page): p.metadata for p in pages}
questions = json.loads(PATH.read_text(encoding="utf-8"))
errors, warnings = [], []

for q in questions:
    qid = q.get("id", "?")
    missing = [k for k in REQUIRED if not q.get(k)]
    if missing or q.get("split") not in ("dev", "test"):
        errors.append(f"{qid}: missing {missing} or bad split {q.get('split')!r}")
        continue
    flt = q.get("filter", {})
    for key, value in flt.items():
        if not any(m.get(key) == value for m in meta.values()):
            errors.append(f"{qid}: filter {key}={value!r} matches no page in the corpus")
    for sid, page, quote in golds(q):
        where = (sid, page)
        if where not in text:
            errors.append(f"{qid}: {sid} p{page} is not a content page")
        elif squash(quote) not in text[where]:
            errors.append(f"{qid}: evidence not found verbatim on {sid} p{page}")
        elif any(meta[where].get(k) != v for k, v in flt.items()):
            errors.append(f"{qid}: filter {flt} excludes its own gold {sid} p{page}")
    listed = {(sid, page) for sid, page, _ in golds(q)}
    unlisted = sorted(k for k, t in text.items() if k not in listed and squash(q["evidence_quote"]) in t)
    if unlisted:
        warnings.append(f"{qid}: primary evidence also appears verbatim on unlisted pages {unlisted}")

ids = [q.get("id") for q in questions]
split = Counter(q.get("split") for q in questions)
filtered = Counter(q.get("split") for q in questions if q.get("filter"))
gold_pages = {s: {(sid, page) for q in questions if q.get("split") == s for sid, page, _ in golds(q)}
              for s in ("dev", "test")}
if len(set(ids)) != len(ids):
    errors.append("duplicate question ids")
if len(questions) < 20 or split["dev"] < 15 or split["test"] < 5:
    errors.append(f"need >=20 questions with >=15 dev / >=5 test, got {dict(split)}")
if sum(filtered.values()) < 3 or filtered["test"] < 1:
    errors.append(f"need >=3 filter questions with >=1 in test, got {dict(filtered)}")
if gold_pages["dev"] & gold_pages["test"]:
    errors.append(f"dev and test share gold pages: {sorted(gold_pages['dev'] & gold_pages['test'])}")

print(f"questions={len(questions)} split={dict(split)} filter={dict(filtered)}")
print("by type:  ", dict(Counter(q.get("type") for q in questions)))
print("by source:", dict(Counter(q.get("gold_source_id") for q in questions)))
for line in warnings:
    print("WARN ", line)
for line in errors:
    print("ERROR", line)
print("Benchmark OK" if not errors else f"{len(errors)} error(s)")
sys.exit(1 if errors else 0)
