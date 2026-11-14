"""Persistent vector store: ChromaDB (PersistentClient, on-disk), cosine space, metadata filter.

Idempotent ingest: chunk IDs are deterministic; per document we compare the stored
`doc_sha256` + chunk-id set with the new one. Unchanged -> skip; changed -> delete that
document's old chunks, then add the new ones (no duplicates, no obsolete chunks).
"""
from __future__ import annotations

from typing import Any

import chromadb

from . import config
from .models import Chunk


class ChromaStore:
    def __init__(self, path=config.CHROMA_DIR, dimensions: int | None = None) -> None:
        self.client = chromadb.PersistentClient(path=str(path))
        self.dimensions = dimensions

    def collection(self, name: str, embed_model: str):
        col = self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "embed_model": embed_model,
                      "dimensions": self.dimensions},
            embedding_function=None,
        )
        stored = col.metadata or {}
        if stored.get("embed_model") != embed_model or stored.get("dimensions") != self.dimensions:
            raise RuntimeError(f"Collection {name} was built with {stored}, not {embed_model}/{self.dimensions}; "
                               f"run with --rebuild.")
        return col

    def drop(self, name: str) -> None:
        try:
            self.client.delete_collection(name)
        except Exception:
            pass

    def upsert_document(self, col, document_id: str, doc_sha: str, chunks: list[Chunk],
                        vectors_fn) -> dict[str, int]:
        """Returns counts {added, deleted, skipped}. vectors_fn(chunks) is only called if needed."""
        existing = col.get(where={"document_id": document_id}, include=["metadatas"])
        old_ids = set(existing["ids"])
        new_ids = {c.chunk_id for c in chunks}
        same_hash = existing["metadatas"] and all(m.get("doc_sha256") == doc_sha for m in existing["metadatas"])
        if old_ids == new_ids and same_hash:
            return {"added": 0, "deleted": 0, "skipped": len(chunks)}
        if old_ids:
            col.delete(ids=list(old_ids))
        vectors = vectors_fn(chunks)
        if len(vectors) != len(chunks):
            raise ValueError("vector/chunk count mismatch")
        for v in vectors:
            if len(v) != self.dimensions:
                raise ValueError(f"vector dim {len(v)} != {self.dimensions}")
        metadatas = []
        for c in chunks:
            md = {k: v for k, v in c.metadata.items() if isinstance(v, (str, int, float, bool))}
            md.update({"document_id": c.document_id, "source": c.source, "page": c.page,
                       "doc_sha256": doc_sha})
            metadatas.append(md)
        for i in range(0, len(chunks), 500):
            col.add(ids=[c.chunk_id for c in chunks[i:i + 500]],
                    embeddings=vectors[i:i + 500],
                    documents=[c.text for c in chunks[i:i + 500]],
                    metadatas=metadatas[i:i + 500])
        return {"added": len(chunks), "deleted": len(old_ids), "skipped": 0}

    @staticmethod
    def search(col, query_vector: list[float], top_k: int = config.TOP_K,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        where = None
        if filters:
            allowed = {"pep_type", "python_version", "status", "document_id"}
            bad = set(filters) - allowed
            if bad:
                raise ValueError(f"filter keys not allowed: {bad}")
            conds = [{k: {"$eq": str(v)}} for k, v in filters.items()]
            where = conds[0] if len(conds) == 1 else {"$and": conds}
        res = col.query(query_embeddings=[query_vector], n_results=top_k, where=where,
                        include=["documents", "metadatas", "distances"])
        hits = []
        for cid, doc, md, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                      res["distances"][0]):
            hits.append({"chunk_id": cid, "text": doc, "metadata": md,
                         "cosine_distance": round(dist, 5), "score": round(1 - dist, 5)})
        return hits
