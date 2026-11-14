"""Check re-ingest behaviour in a TEMPORARY Chroma directory (does not touch chroma_db/).

1. ingest pep-0257 (strategy B) -> N chunks
2. ingest again unchanged       -> all skipped, still N
3. ingest a "changed" version (last page removed, new sha) -> old chunks deleted,
   new ones added, no stale IDs left.
Run: python scripts/check_reingest_change.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402
from src.chunking import build_chunks  # noqa: E402
from src.embeddings import get_embedder  # noqa: E402
from src.ingestion import load_pages  # noqa: E402
from src.store import ChromaStore  # noqa: E402


def main() -> None:
    pages = [p for p in load_pages() if p.document_id == "pep-0257"]
    spec = config.STRATEGIES["B"]
    emb = get_embedder()
    vec = lambda cs: emb.embed_documents([emb.doc_input(c) for c in cs])  # noqa: E731
    out = {}
    # Chroma keeps index files memory-mapped on Windows -> ignore cleanup errors
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = ChromaStore(path=Path(tmp), dimensions=emb.dimensions)
        col = store.collection("reingest_test", emb.model_name)
        v1 = build_chunks(pages, spec)
        out["1_first_ingest"] = {**store.upsert_document(col, "pep-0257", "sha-v1", v1, vec), "count": col.count()}
        out["2_same_version"] = {**store.upsert_document(col, "pep-0257", "sha-v1", v1, vec), "count": col.count()}
        v2 = build_chunks(pages[:-1], spec)  # simulate an edited document: last page removed
        out["3_changed_version"] = {**store.upsert_document(col, "pep-0257", "sha-v2", v2, vec),
                                    "count": col.count(), "expected_count": len(v2)}
        ids_now = set(col.get()["ids"])
        out["stale_ids_left"] = sorted(ids_now - {c.chunk_id for c in v2})
        out["duplicate_free"] = col.count() == len(ids_now) == len(v2)
        del col, store  # release file handles before temp dir cleanup (Windows)
    print(json.dumps(out, indent=2))
    config.RESULTS_DIR.mkdir(exist_ok=True)
    (config.RESULTS_DIR / "reingest_change_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    if out["stale_ids_left"] or not out["duplicate_free"]:
        raise SystemExit("re-ingest check FAILED")


if __name__ == "__main__":
    main()
