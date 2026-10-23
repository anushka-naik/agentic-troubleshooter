"""Hybrid retrieval: dense (FAISS) and lexical (BM25) rankings fused with RRF.

Error messages are full of exact tokens (``NoneType``, ``JSONDecodeError``,
``__init__``) that embedding models blur together, while paraphrased questions
("why does my list keep growing") need semantic matching. Reciprocal rank
fusion combines both without having to calibrate their score scales.
"""

import json
import re
from dataclasses import dataclass

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langsmith import traceable
from rank_bm25 import BM25Okapi

from troubleshooter.config import Settings
from troubleshooter.rag.indexer import CHUNKS_FILE, build_index, get_embeddings, index_exists

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_RRF_K = 60


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text)]


@dataclass
class RetrievedChunk:
    chunk_id: str
    title: str
    url: str
    text: str
    score: float


class HybridRetriever:
    def __init__(self, store: FAISS, chunks: list[Document]):
        self._store = store
        self._chunks = {c.metadata["chunk_id"]: c for c in chunks}
        self._ids = [c.metadata["chunk_id"] for c in chunks]
        self._bm25 = BM25Okapi([tokenize(c.page_content) for c in chunks])

    @classmethod
    def from_settings(cls, settings: Settings, rebuild: bool = False) -> "HybridRetriever":
        if rebuild or not index_exists(settings):
            build_index(settings)
        store = FAISS.load_local(
            str(settings.index_dir),
            get_embeddings(settings),
            # The index is produced locally by build_index, never downloaded.
            allow_dangerous_deserialization=True,
        )
        raw = json.loads((settings.index_dir / CHUNKS_FILE).read_text(encoding="utf-8"))
        return cls(store, [Document(**item) for item in raw])

    @property
    def size(self) -> int:
        return len(self._ids)

    def _dense_ranking(self, query: str, depth: int) -> list[str]:
        hits = self._store.similarity_search(query, k=depth)
        return [hit.metadata["chunk_id"] for hit in hits]

    def _lexical_ranking(self, query: str, depth: int) -> list[str]:
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._ids[i] for i in order[:depth] if scores[i] > 0]

    @traceable(run_type="retriever", name="hybrid_search")
    def search(self, queries: list[str], k: int = 8) -> list[RetrievedChunk]:
        """Fuse dense and lexical rankings across all queries into one list."""
        depth = max(k * 2, 10)
        fused: dict[str, float] = {}
        for query in queries:
            for ranking in (self._dense_ranking(query, depth), self._lexical_ranking(query, depth)):
                for rank, chunk_id in enumerate(ranking):
                    fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)

        best = sorted(fused.items(), key=lambda item: item[1], reverse=True)[:k]
        results = []
        for chunk_id, score in best:
            chunk = self._chunks[chunk_id]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    title=chunk.metadata["title"],
                    url=chunk.metadata["url"],
                    text=chunk.page_content,
                    score=round(score, 4),
                )
            )
        return results
