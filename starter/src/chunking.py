"""Fixed-size and structure-aware chunking. Every chunk is an exact slice of its page text."""
import re

from .models import Chunk, DocumentPage

TERMINAL = re.compile(r"[.!?:][\"')\]”’]*$")  # line ends a sentence
BLOCK_START = re.compile(r"\d{1,2}-\d{1,3}\. |• |(Table|Figure) \d")  # FM numbered paragraph, bullet, caption
SENTENCE_END = re.compile(r"[.!?][\"')\]”’]*\s+")
HEADING_MAX = 60  # a heading is a short line between two sentences


def _chunk(page: DocumentPage, name: str, index: int, start: int, end: int) -> Chunk:
    return Chunk(f"{page.document_id}:p{page.page:03d}:{name}:{index:02d}", page.document_id, page.source,
                 page.page, page.text[start:end], {**page.metadata, "char_start": start, "char_end": end})


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Sliding character windows of `size` that share `overlap` characters; boundaries ignore structure."""
    if not 0 <= overlap < size:
        raise ValueError(f"need 0 <= overlap < size, got size={size} overlap={overlap}")
    starts = range(0, max(len(page.text) - overlap, 1), size - overlap)
    return [_chunk(page, "fixed", i, s, min(s + size, len(page.text))) for i, s in enumerate(starts)]


def block_starts(text: str) -> list[int]:
    """Offsets where a paragraph, bullet, caption or heading starts.

    ponytail: line-shape heuristics, the PDF text layer has no blank lines or font info. Narrow columns
    over-segment at sentence ends and Title Case table cells can look like headings; use a layout-aware
    parser if that hurts.
    """
    lines = text.split("\n")
    width = sorted(map(len, lines))[int(len(lines) * 0.9)]  # ~full line width on this page
    ended = [bool(TERMINAL.search(line)) for line in lines]

    def heading(i: int) -> bool:
        line = lines[i]
        return (len(line) <= HEADING_MAX and line[:1].isupper() and not ended[i]
                and not BLOCK_START.match(line) and (i == 0 or ended[i - 1]))

    starts, offset = [], 0
    for i, line in enumerate(lines):
        # A heading opens a block and never closes one, so it stays glued to the text it introduces.
        if i and not heading(i - 1) and (BLOCK_START.match(line) or heading(i)
                                         or (ended[i - 1] and len(lines[i - 1]) < 0.8 * width)):
            starts.append(offset)
        offset += len(line) + 1
    return starts


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Pack whole blocks up to `max_size`; split an oversized block at a sentence, then line, then word."""
    text = page.text
    levels = [block_starts(text), *([m.end() for m in re.finditer(pattern, text)]
                                    for pattern in (SENTENCE_END, r"\n", r" "))]
    spans, start = [], 0
    while len(text) - start > max_size:
        limit = start + max_size
        # Latest cut in the window at the strongest level that has one; hard cut if a single word overflows.
        cut = next((max(inside) for cuts in levels if (inside := [c for c in cuts if start < c <= limit])), limit)
        spans.append((start, cut))
        start = cut
    spans.append((start, len(text)))
    # Trailing whitespace stays out of the chunk so offsets and text agree with the page slice.
    return [_chunk(page, "para", i, s, s + len(text[s:e].rstrip())) for i, (s, e) in enumerate(spans)]


def demo() -> None:
    """Self-check: python -m src.chunking"""
    text = "\n".join([
        "Nutritional Readiness",
        "8-15. Soldiers need to limit sodium consumption. Healthy eating patterns limit sodium to less than 2,300",
        "milligrams per day for adults.",
        "BODY COMPOSITION",
        "8-17. The body is comprised of water, protein, minerals, and fat. A two-compartment model of body",
        "composition divides the body into a fat component and fat-free component.",
        "• 12 fluid ounces of regular beer (5 percent alcohol).",
    ])
    page = DocumentPage("doc", "doc.pdf", 7, text, {"section": "Chapter 8"})

    fixed = fixed_size(page, 100, 20)
    assert all(c.text == text[c.metadata["char_start"]:c.metadata["char_end"]] for c in fixed)
    assert all(len(c.text) == 100 for c in fixed[:-1]) and fixed[-1].metadata["char_end"] == len(text)
    assert all(b.metadata["char_start"] == a.metadata["char_end"] - 20 for a, b in zip(fixed, fixed[1:]))
    assert len(fixed_size(DocumentPage("d", "s", 1, "x" * 100), 100, 20)) == 1  # no overlap-only tail chunk
    assert fixed[0].chunk_id == "doc:p007:fixed:00" and fixed[0].metadata["section"] == "Chapter 8"

    blocks = [text[s:].split("\n")[0] for s in block_starts(text)]
    assert blocks == ["BODY COMPOSITION", "• 12 fluid ounces of regular beer (5 percent alcohol)."], blocks

    para = by_paragraph(page, 250)
    assert [c.text.split("\n")[0][:16] for c in para] == ["Nutritional Read", "BODY COMPOSITION"], para
    assert all(len(c.text) <= 250 and c.text == text[c.metadata["char_start"]:c.metadata["char_end"]] for c in para)
    assert " ".join(c.text for c in para).split() == text.split()  # nothing lost, nothing repeated
    tight = by_paragraph(page, 80)  # forces sentence, line and word-level cuts
    assert all(len(c.text) <= 80 for c in tight) and " ".join(c.text for c in tight).split() == text.split()
    assert by_paragraph(DocumentPage("d", "s", 1, "y" * 25), 10)[-1].text == "y" * 5  # hard cut
    print("chunking OK")


if __name__ == "__main__":
    demo()
