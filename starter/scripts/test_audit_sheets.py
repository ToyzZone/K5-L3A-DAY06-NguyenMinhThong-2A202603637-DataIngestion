"""Write the manual audit sheets for metadata and grounding from the saved test traces.

Sample: the first five test questions by ID, a rule fixed before the test run. Hit flags are left out so
the labels stay independent of the automatic score. Labels are filled in by hand afterwards.

Run from starter/ after `python -m src.run test`:  python -m scripts.test_audit_sheets
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "results" / "audit"
SAMPLE = 5

traces = {name: sorted(json.loads((ROOT / "results" / "test" / f"traces_{name}.json").read_text(encoding="utf-8")),
                       key=lambda t: t["id"])[:SAMPLE] for name in "ABC"}

# Metadata: one row per distinct retrieved chunk; `retrieved_for` lists every (config, question, rank) it covers.
chunks: dict[str, dict] = {}
for name, sample in traces.items():
    for trace in sample:
        for hit in trace["top3"]:
            row = chunks.setdefault(hit["chunk_id"], {"chunk_id": hit["chunk_id"], **hit["metadata"], "text": hit["text"],
                                                      "retrieved_for": [], "metadata_correct": None, "error": ""})
            row["retrieved_for"].append(f"{name} {trace['id']} #{hit['rank']}")

# Grounding: one row per question x config, judged on the whole top-3.
grounding = []
for i in range(SAMPLE):
    for name in "ABC":
        trace = traces[name][i]
        ids = [h["chunk_id"] for h in trace["top3"]]
        same = next((o for o in "ABC" if o < name and [h["chunk_id"] for h in traces[o][i]["top3"]] == ids), None)
        grounding.append({
            "id": trace["id"], "strategy": name, "question": trace["question"],
            "expected_answer": trace["expected_answer"], "filter_applied": trace["filter_applied"],
            "same_top3_as": same,  # identical chunks in identical order: the label can be copied
            "top3": [{"rank": h["rank"], "chunk_id": h["chunk_id"], "page": h["metadata"]["page"],
                      "section": h["metadata"]["section"], "text": h["text"]} for h in trace["top3"]],
            "score_0_2": None, "reason": ""})

AUDIT.mkdir(parents=True, exist_ok=True)
for name, rows in (("metadata.json", list(chunks.values())), ("grounding.json", grounding)):
    with (AUDIT / name).open("x", encoding="utf-8") as f:  # "x": refuse to overwrite hand-written labels
        json.dump(rows, f, ensure_ascii=False, indent=2)
records = sum(len(r["retrieved_for"]) for r in chunks.values())
print(f"metadata.json: {len(chunks)} distinct chunks covering {records} retrieved records; "
      f"grounding.json: {len(grounding)} rows ({[t['id'] for t in traces['A']]} x A/B/C) -> {AUDIT}")
