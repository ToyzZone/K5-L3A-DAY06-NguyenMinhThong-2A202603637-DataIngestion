"""Score retrieved chunks against gold evidence and keep per-query traces.

Only the automatic retrieval metrics live here; coherence and grounding are labelled by hand.
"""
from collections import defaultdict
from typing import Any


def squash(text: str) -> str:
    """Evidence is matched case-sensitively after collapsing whitespace (chunks keep line breaks)."""
    return " ".join(text.split())


def golds(question: dict[str, Any]) -> list[tuple[str, int, str]]:
    """Every accepted (source_id, page, evidence_quote): the primary gold plus documented alternatives."""
    return [(question["gold_source_id"], question["gold_page"], question["evidence_quote"])] + [
        (g["source_id"], g["page"], g["evidence_quote"]) for g in question.get("alt_gold", [])]


def has_evidence(question: dict[str, Any], document_id: str, page: int, text: str) -> bool:
    """A hit = the text sits on a gold page and contains that page's whole evidence quote."""
    text = squash(text)
    return any(document_id == sid and page == gold_page and squash(quote) in text
               for sid, gold_page, quote in golds(question))


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    gold_pages = {(sid, page) for sid, page, _ in golds(question)}
    top = [{"rank": rank, "chunk_id": h["chunk_id"], "score": h["score"],
            "hit": has_evidence(question, h["metadata"]["document_id"], h["metadata"]["page"], h["text"]),
            "on_gold_page": (h["metadata"]["document_id"], h["metadata"]["page"]) in gold_pages,
            "metadata": h["metadata"], "text": h["text"]} for rank, h in enumerate(hits, 1)]
    wanted = question.get("filter")
    return {
        **{k: question[k] for k in ("id", "split", "type", "question", "expected_answer")},
        "gold": [{"source_id": s, "page": p, "evidence_quote": q} for s, p, q in golds(question)],
        "filter": wanted,
        "hit_at_1": bool(top) and top[0]["hit"],
        "hit_at_3": any(t["hit"] for t in top[:3]),
        # Does the top-3 stay inside the scope the question asked for? None when the question has no filter.
        "filter_compliant": all(t["metadata"].get(k) == v for t in top[:3] for k, v in wanted.items()) if wanted else None,
        "top3": top[:3],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts (never bare percentages) per strategy and split: {strategy: {split: {...}}}."""
    groups = defaultdict(list)
    for trace in traces:
        groups[trace["strategy"], trace["split"]].append(trace)
    out: dict[str, Any] = defaultdict(dict)
    for (strategy, split), group in sorted(groups.items()):
        with_filter = [t for t in group if t["filter"]]
        out[strategy][split] = {
            "n": len(group),
            "hit_at_1": sum(t["hit_at_1"] for t in group),
            "hit_at_3": sum(t["hit_at_3"] for t in group),
            "filter_questions": len(with_filter),
            "filter_compliant": sum(t["filter_compliant"] for t in with_filter),
        }
    return dict(out)


def demo() -> None:
    """Self-check: python -m src.evaluation"""
    q = {"id": "q", "split": "dev", "type": "direct", "question": "?", "expected_answer": "a",
         "gold_source_id": "doc", "gold_page": 5, "evidence_quote": "less than 2,300 milligrams",
         "alt_gold": [{"source_id": "doc", "page": 9, "evidence_quote": "under 2,300 mg"}],
         "filter": {"section": "Ch 8"}}

    def hit(page: int, text: str, section: str = "Ch 8", doc: str = "doc") -> dict:
        return {"chunk_id": f"{doc}:{page}", "text": text, "score": 0.5,
                "metadata": {"document_id": doc, "page": page, "section": section}}

    right = hit(5, "sodium to less than 2,300\nmilligrams per day")  # quote spans a line break
    half = hit(5, "sodium to less than 2,300")                       # right page, evidence cut off
    wrong_page = hit(6, "less than 2,300 milligrams")
    alt = hit(9, "keep it under 2,300 mg", section="Ch 9")
    other_doc = hit(5, "less than 2,300 milligrams", doc="other")

    t = evaluate_query(q, [half, right, wrong_page])
    assert (t["hit_at_1"], t["hit_at_3"], t["filter_compliant"]) == (False, True, True)
    assert [x["on_gold_page"] for x in t["top3"]] == [True, True, False]
    t2 = evaluate_query(q, [alt, half, half])
    assert (t2["hit_at_1"], t2["hit_at_3"], t2["filter_compliant"]) == (True, True, False)
    t3 = evaluate_query(q, [wrong_page, other_doc, half, right])  # the 4th result must not count
    assert (t3["hit_at_1"], t3["hit_at_3"]) == (False, False)
    t4 = evaluate_query({k: v for k, v in q.items() if k != "filter"}, [])
    assert (t4["hit_at_1"], t4["hit_at_3"], t4["filter_compliant"]) == (False, False, None)
    for trace, strategy in ((t, "A"), (t2, "A"), (t3, "B"), (t4, "B")):
        trace["strategy"] = strategy
    assert summarize([t, t2, t3, t4]) == {
        "A": {"dev": {"n": 2, "hit_at_1": 1, "hit_at_3": 2, "filter_questions": 2, "filter_compliant": 1}},
        "B": {"dev": {"n": 2, "hit_at_1": 0, "hit_at_3": 0, "filter_questions": 1, "filter_compliant": 1}}}
    print("evaluation OK")


if __name__ == "__main__":
    demo()
