"""Shared data contracts; keep traceability from chunk back to source."""
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class DocumentPage:
    """One traceable source unit ("page") of a document."""
    page_id: str          # e.g. pep-0008-p03
    document_id: str      # e.g. pep-0008
    source: str           # repo-relative path of the raw file
    page: int             # 1-based unit number inside the document
    text: str             # normalized text of the unit
    char_start: int       # boundaries in the normalized document text
    char_end: int
    headings: list[tuple[int, str]] = field(default_factory=list)  # (offset in page, section path)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    source: str
    page: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
