"""Read PEP reStructuredText sources, normalize them and split into traceable units.

Each PEP is non-paginated, so following GUIDE.md a "page" is an ordered unit of at
least 1500 normalized characters, cut only at block (blank-line) boundaries.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from . import config
from .models import DocumentPage

HEADER_RE = re.compile(r"^([A-Za-z][A-Za-z-]*):\s*(.*)$")
UNDERLINE_RE = re.compile(r"^([=\-~^'\"`#*+])\1{2,}\s*$")
EMACS_RE = re.compile(r"\n\.\.\s*\n\s+Local Variables:.*\Z", re.S)


def parse_header(raw: str) -> tuple[dict[str, str], str]:
    """Split the RFC-822 style PEP preamble from the body."""
    lines = raw.splitlines()
    header: dict[str, str] = {}
    key = None
    i = 0
    for i, line in enumerate(lines):
        if not line.strip():
            break
        m = HEADER_RE.match(line)
        if m:
            key = m.group(1)
            header[key] = m.group(2).strip()
        elif key and line.startswith((" ", "\t")):
            header[key] += " " + line.strip()
        else:
            raise ValueError(f"Unexpected header line: {line!r}")
    return header, "\n".join(lines[i + 1:])


def normalize_text(text: str) -> str:
    """NFC Unicode, unify newlines/spaces, drop rst comments; keep paragraph & code structure."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    text = text.replace(" ", " ").replace("​", "")
    text = EMACS_RE.sub("\n", text)
    out = []
    for line in text.split("\n"):
        stripped = line.strip()
        # rst link targets / comments / directives with no content value
        if re.match(r"^\.\.\s+(_[^:]+:.*|\|.*|contents::.*|code-block::.*|highlight::.*|sectnum::.*)$", stripped):
            continue
        if stripped == ".." or stripped.startswith(".. image::"):
            continue
        # directive options (e.g. ":class: good" under code-block); PEP 8 already marks
        # examples with "# Correct:" / "# Wrong:" comments, so no information is lost.
        if re.match(r"^:(class|alt|caption|name|width|linenos|target):(\s.*)?$", stripped):
            continue
        out.append(line.rstrip())
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def split_blocks(text: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of blank-line separated blocks."""
    blocks = []
    for m in re.finditer(r"(?:[^\n]|\n(?!\n))+", text):
        if m.group(0).strip():
            lead = len(m.group(0)) - len(m.group(0).lstrip("\n"))  # skip separator newline
            blocks.append((m.start() + lead, m.end()))
    return blocks


def find_headings(text: str) -> list[tuple[int, int, str]]:
    """Detect rst section titles: a text line underlined with a punctuation line.

    Returns (offset_of_title_line, level, title)."""
    lines = text.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    levels: list[str] = []
    found = []
    for i in range(len(lines) - 1):
        title, under = lines[i], lines[i + 1]
        if (title.strip() and not title.startswith(" ") and UNDERLINE_RE.match(under)
                and len(under.strip()) >= len(title.strip()) and not UNDERLINE_RE.match(title)):
            ch = under.strip()[0]
            if ch not in levels:
                levels.append(ch)
            found.append((offsets[i], levels.index(ch) + 1, title.strip()))
    return found


def section_paths(headings: list[tuple[int, int, str]]) -> list[tuple[int, str]]:
    """Convert headings to (offset, 'Top > Sub') paths."""
    stack: list[tuple[int, str]] = []
    paths = []
    for off, level, title in headings:
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        paths.append((off, " > ".join(t for _, t in stack)))
    return paths


def section_at(paths: list[tuple[int, str]], offset: int) -> str:
    current = "(preamble)"
    for off, path in paths:
        if off <= offset:
            current = path
        else:
            break
    return current


def load_pep(path: Path) -> tuple[dict, str, list[DocumentPage], list[str]]:
    """Read one PEP file -> (doc_info, normalized_text, pages, warnings)."""
    warnings: list[str] = []
    raw_bytes = path.read_bytes()
    raw = raw_bytes.decode("utf-8")  # fail loudly on bad encoding
    header, body = parse_header(raw)
    norm = normalize_text(body)
    document_id = path.stem
    source = path.relative_to(config.ROOT).as_posix()
    paths = section_paths(find_headings(norm))

    # Group blocks into units of >= UNIT_TARGET_CHARS.
    blocks = split_blocks(norm)
    if not blocks:
        warnings.append(f"{document_id}: empty body")
    units: list[tuple[int, int]] = []
    start = None
    for b_start, b_end in blocks:
        if start is None:
            start = b_start
        if b_end - start >= config.UNIT_TARGET_CHARS:
            units.append((start, b_end))
            start = None
    if start is not None:
        last_end = blocks[-1][1]
        if units and last_end - start < config.UNIT_MIN_CHARS:
            units[-1] = (units[-1][0], last_end)  # merge short tail into previous unit
        else:
            units.append((start, last_end))

    meta = {
        "title": header.get("Title", ""),
        "pep_number": int(header["PEP"]),
        "pep_type": header.get("Type", ""),
        "status": header.get("Status", ""),
        "created": header.get("Created", ""),
        "python_version": header.get("Python-Version", "n/a"),
    }
    pages = []
    for idx, (s, e) in enumerate(units, start=1):
        text = norm[s:e]
        n = len(text.strip())
        if n < config.UNIT_MIN_CHARS:
            warnings.append(f"{document_id} p{idx}: only {n} chars (< {config.UNIT_MIN_CHARS})")
        local_heads = [(off - s, p) for off, p in paths if s <= off < e]
        # carry in the section active at the start of the page
        local_heads.insert(0, (0, section_at(paths, s))) if not local_heads or local_heads[0][0] != 0 else None
        pages.append(DocumentPage(
            page_id=f"{document_id}-p{idx:02d}", document_id=document_id, source=source,
            page=idx, text=text, char_start=s, char_end=e, headings=local_heads,
            metadata=dict(meta),
        ))
    info = {
        "source_id": document_id,
        "title": meta["title"],
        "source_path_or_url": f"{config.PEPS_REPO}/blob/{config.PEPS_COMMIT}/peps/{path.name}",
        "local_path": source,
        "license_or_permission": None,  # filled below from document text
        "accessed_at": config.ACCESSED_AT,
        "snapshot": f"python/peps@{config.PEPS_COMMIT}",
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "raw_chars": len(raw),
        "normalized_chars": len(norm),
        "pep_type": meta["pep_type"],
        "python_version": meta["python_version"],
        "status": meta["status"],
        "created": meta["created"],
    }
    if "CC0-1.0-Universal" in raw:
        info["license_or_permission"] = ("Public domain or CC0-1.0-Universal "
                                         "(statement in the document's Copyright section)")
    elif "placed in the public domain" in raw:
        info["license_or_permission"] = "Public domain (statement in the document's Copyright section)"
    else:
        warnings.append(f"{document_id}: no licence statement found -> excluded")
        return info, norm, [], warnings
    return info, norm, pages, warnings


def build_corpus() -> tuple[list[DocumentPage], dict]:
    all_pages: list[DocumentPage] = []
    docs, warnings = [], []
    for sid in config.SOURCES:
        path = config.RAW_DIR / f"{sid}.rst"
        if not path.exists():
            raise FileNotFoundError(f"Missing source {path}; see README (download step).")
        info, _norm, pages, warns = load_pep(path)
        warnings.extend(warns)
        info["pages"] = [{"page_id": p.page_id, "page": p.page, "char_start": p.char_start,
                          "char_end": p.char_end, "chars": len(p.text)} for p in pages]
        info["page_count"] = len(pages)
        docs.append(info)
        all_pages.extend(pages)
    manifest = {
        "corpus": "Python Enhancement Proposals (8 PEPs)",
        "page_rule": (f"Sources are non-paginated reStructuredText. After normalization, each document "
                      f"is split in order at blank-line boundaries into units of >= "
                      f"{config.UNIT_TARGET_CHARS} chars; a final tail < {config.UNIT_MIN_CHARS} chars is "
                      f"merged into the previous unit. Every unit therefore has >= {config.UNIT_MIN_CHARS} "
                      f"normalized chars. The PEP preamble (header fields) is removed from text and kept "
                      f"as metadata. No duplication is used."),
        "total_documents": len(docs),
        "total_pages": len(all_pages),
        "total_normalized_chars": sum(len(p.text) for p in all_pages),
        "min_page_chars": min(len(p.text) for p in all_pages),
        "warnings": warnings,
        "documents": docs,
    }
    return all_pages, manifest


def main() -> None:
    pages, manifest = build_corpus()
    config.PAGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with config.PAGES_PATH.open("w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
    config.MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"pages={manifest['total_pages']} chars={manifest['total_normalized_chars']} "
          f"min_page_chars={manifest['min_page_chars']} warnings={manifest['warnings']}")
    for d in manifest["documents"]:
        print(f"  {d['source_id']}: {d['page_count']} pages, {d['pep_type']}, py {d['python_version']}")


def load_pages() -> list[DocumentPage]:
    pages = []
    with config.PAGES_PATH.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            d["headings"] = [tuple(h) for h in d["headings"]]
            pages.append(DocumentPage(**d))
    return pages


if __name__ == "__main__":
    main()
