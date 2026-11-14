"""Fixed-size (A) and structure-aware (B/C) chunking. Chunks never cross page boundaries,
so every chunk keeps an exact (document_id, page) trace plus char offsets in the page."""
from __future__ import annotations

import hashlib
import re

from .ingestion import section_at
from .models import Chunk, DocumentPage

UNDERLINE_RE = re.compile(r"^([=\-~^'\"`#*+])\1{2,}\s*$")


def _make_chunk(strategy: str, page: DocumentPage, idx: int, start: int, end: int) -> Chunk:
    text = page.text[start:end].strip()
    md = dict(page.metadata)
    md.update({
        "page_id": page.page_id,
        "section": section_at(page.headings, start),
        "char_start": start,
        "char_end": end,
        "chunk_chars": len(text),
        "strategy_chunking": strategy,
        "content_sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
    })
    return Chunk(chunk_id=f"{page.page_id}-c{idx:03d}", document_id=page.document_id,
                 source=page.source, page=page.page, text=text, metadata=md)


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Character windows of `size` with `overlap`; ignores sentences/headings on purpose."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks, start, idx = [], 0, 0
    n = len(page.text)
    while start < n:
        end = min(start + size, n)
        if page.text[start:end].strip():
            chunks.append(_make_chunk("fixed", page, idx, start, end))
            idx += 1
        if end == n:
            break
        start = end - overlap
    return chunks


def _blocks(text: str) -> list[tuple[int, int, bool]]:
    """(start, end, is_heading) for blank-line separated blocks; a heading block is a
    title line followed by its rst underline."""
    out = []
    for m in re.finditer(r"(?:[^\n]|\n(?!\n))+", text):
        block = m.group(0)
        if not block.strip():
            continue
        lead = len(block) - len(block.lstrip("\n"))  # regex may start on a separator newline
        block = block[lead:]
        m_start = m.start() + lead
        lines = block.rstrip("\n").split("\n")
        is_heading = len(lines) >= 2 and bool(UNDERLINE_RE.match(lines[1])) and lines[0].strip() != ""
        if is_heading and len(lines) > 2:
            # heading immediately followed by text without a blank line: split it off
            cut = m_start + len(lines[0]) + 1 + len(lines[1])
            out.append((m_start, cut, True))
            out.append((cut + 1, m.end(), False))
        else:
            out.append((m_start, m.end(), is_heading))
    return out


def _split_long(text: str, start: int, end: int, max_size: int) -> list[tuple[int, int]]:
    """Split an oversized block at sentence ends, then line ends, then hard cut."""
    pieces, s = [], start
    while end - s > max_size:
        window = text[s:s + max_size]
        cut = max(window.rfind(". "), window.rfind(".\n"))
        if cut < max_size * 0.4:
            cut = window.rfind("\n")
        if cut < max_size * 0.4:
            cut = max_size - 1
        pieces.append((s, s + cut + 1))
        s = s + cut + 1
        while s < end and text[s] in " \n":
            s += 1
    if s < end:
        pieces.append((s, end))
    return pieces


def by_structure(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group consecutive paragraphs under the same heading up to `max_size` chars.

    A heading always starts a new chunk (and stays attached to the following text);
    oversized paragraphs are split at sentence boundaries."""
    text = page.text
    units: list[tuple[int, int, bool]] = []
    for s, e, is_h in _blocks(text):
        if not is_h and e - s > max_size:
            units.extend((a, b, False) for a, b in _split_long(text, s, e, max_size))
        else:
            units.append((s, e, is_h))

    chunks, idx = [], 0
    cur_start = cur_end = None
    cur_only_heading = False
    for s, e, is_h in units:
        if cur_start is None:
            cur_start, cur_end, cur_only_heading = s, e, is_h
            continue
        starts_new = is_h and not cur_only_heading
        too_big = (e - cur_start) > max_size and not cur_only_heading
        if starts_new or too_big:
            chunks.append(_make_chunk("structure", page, idx, cur_start, cur_end))
            idx += 1
            cur_start, cur_end, cur_only_heading = s, e, is_h
        else:
            cur_end = e
            cur_only_heading = cur_only_heading and is_h
    if cur_start is not None:
        chunks.append(_make_chunk("structure", page, idx, cur_start, cur_end))
    return chunks


def build_chunks(pages: list[DocumentPage], spec: dict) -> list[Chunk]:
    out: list[Chunk] = []
    for p in pages:
        if spec["chunking"] == "fixed":
            out.extend(fixed_size(p, spec["size"], spec["overlap"]))
        elif spec["chunking"] == "structure":
            out.extend(by_structure(p, spec["max_size"]))
        else:
            raise ValueError(spec["chunking"])
    return out
