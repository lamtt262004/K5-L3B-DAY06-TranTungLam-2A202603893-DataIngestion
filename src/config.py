"""Central configuration shared by every strategy (same corpus, model, store, metric)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# "local" (default, reported results) or "openai". One provider for ALL strategies of a run.
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "local").strip().lower() or "local"
if EMBED_PROVIDER not in {"local", "openai"}:
    raise ValueError(f"EMBED_PROVIDER must be 'local' or 'openai', got {EMBED_PROVIDER!r}")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
_SUFFIX = "" if EMBED_PROVIDER == "local" else f"_{EMBED_PROVIDER}"

RAW_DIR = ROOT / "data" / "raw"
PAGES_PATH = ROOT / "data" / "pages.jsonl"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
QUESTIONS_PATH = ROOT / "benchmark" / "questions.jsonl"
RESULTS_DIR = ROOT / f"results{_SUFFIX}"
CHROMA_DIR = ROOT / "chroma_db"

# Snapshot of https://github.com/python/peps used for the corpus.
PEPS_REPO = "https://github.com/python/peps"
PEPS_COMMIT = "2ace2311c6a460c71c92dc64046c6f299de2a3a7"
ACCESSED_AT = "2026-11-14"
SOURCES = ["pep-0001", "pep-0008", "pep-0257", "pep-0498",
           "pep-0557", "pep-0572", "pep-0634", "pep-0636"]

# A "page" = ordered unit of >= 1500 normalized chars (GUIDE.md, non-paginated sources).
UNIT_TARGET_CHARS = 2000
UNIT_MIN_CHARS = 1500

# Embedding model: identical for A/B/C.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_MAX_SEQ = 512
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
EMBED_BATCH = 64

STRATEGIES = {
    "A": {"collection": f"day6_A_fixed500{_SUFFIX}", "chunking": "fixed", "size": 500, "overlap": 50,
          "use_filter": False},
    "B": {"collection": f"day6_B_structure1200{_SUFFIX}", "chunking": "structure", "max_size": 1200,
          "use_filter": False},
    # C re-uses B's index: the ONLY difference B -> C is the metadata filter at query time.
    "C": {"collection": f"day6_B_structure1200{_SUFFIX}", "chunking": "structure", "max_size": 1200,
          "use_filter": True},
}
TOP_K = 3
