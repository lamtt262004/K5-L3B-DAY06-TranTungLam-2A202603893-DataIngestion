"""Real local embedding model (Sentence Transformers). No mock / random fallback."""
from __future__ import annotations

from . import config


class BgeEmbedder:
    """BAAI/bge-small-en-v1.5: 384-d, max 512 tokens, L2-normalized (cosine).

    Per the model card, queries get the retrieval instruction prefix and documents do not.
    """

    def __init__(self, model_name: str = config.EMBED_MODEL) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_name, device=self.device)  # raises if unavailable
        self.model.max_seq_length = config.EMBED_MAX_SEQ
        self.dimensions = self.model.get_sentence_embedding_dimension()
        self.tokenizer = self.model.tokenizer

    def doc_input(self, chunk) -> str:
        """Text actually embedded for a chunk: same rule for every strategy."""
        md = chunk.metadata
        return f"{md['title']} — {md['section']}\n{chunk.text}"

    def count_tokens(self, texts: list[str]) -> list[int]:
        return [len(self.tokenizer(t, add_special_tokens=True)["input_ids"]) for t in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(texts, batch_size=config.EMBED_BATCH, normalize_embeddings=True,
                                 show_progress_bar=False, convert_to_numpy=True)
        return vecs.tolist()

    def embed_query(self, question: str) -> list[float]:
        vec = self.model.encode([config.QUERY_INSTRUCTION + question], normalize_embeddings=True,
                                show_progress_bar=False, convert_to_numpy=True)[0]
        return vec.tolist()


class OpenAIEmbedder:
    """OpenAI embeddings API (optional; EMBED_PROVIDER=openai). Raises on any API error."""

    PRICE_PER_1M = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}

    def __init__(self, model_name: str = config.OPENAI_EMBED_MODEL) -> None:
        import os
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("EMBED_PROVIDER=openai but OPENAI_API_KEY is empty in .env")
        self.model_name = model_name
        self.device = "openai-api"
        self.tokens_used = 0
        self.dimensions = len(self._call(["dimension probe"])[0])
        self.tokens_used = 0  # probe not counted in ingest stats

    def _call(self, texts: list[str]) -> list[list[float]]:
        import json
        import urllib.request
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps({"model": self.model_name, "input": texts}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:  # HTTPError propagates (no fallback)
            body = json.loads(resp.read())
        self.tokens_used += body.get("usage", {}).get("total_tokens", 0)
        return [d["embedding"] for d in sorted(body["data"], key=lambda d: d["index"])]

    def doc_input(self, chunk) -> str:
        md = chunk.metadata
        return f"{md['title']} — {md['section']}\n{chunk.text}"

    def count_tokens(self, texts: list[str]) -> list[int]:
        return [max(1, len(t) // 4) for t in texts]  # rough estimate; exact usage in tokens_used

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out = []
        for i in range(0, len(texts), 256):
            out.extend(self._call(texts[i:i + 256]))
        return out

    def embed_query(self, question: str) -> list[float]:
        return self._call([question])[0]  # OpenAI models use no query instruction

    def cost_usd(self) -> float:
        return round(self.tokens_used / 1e6 * self.PRICE_PER_1M.get(self.model_name, 0.0), 6)


def get_embedder():
    return OpenAIEmbedder() if config.EMBED_PROVIDER == "openai" else BgeEmbedder()
