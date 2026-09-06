"""L6 — local hybrid retrieval over EvidenceSpans. Returns spans, never prose.

Dense half: an embedding model reachable through the L1 model registry (see
`_EMBED_MODEL_ID` below). Sparse half: a dependency-free term-frequency vector scored
server-side by Qdrant's IDF modifier (Qdrant's documented BM25-without-a-library
approach) — no separate BM25 library is installed, per docs/L6_KB.md's "pick one and
document it".

Deviation from docs/L6_KB.md, recorded in PROGRESS.md: the doc specifies
`SentenceTransformer(SETTINGS.embedding_model_path)` (BGE-M3, 1024d). No such local
sentence-transformers directory is staged on this dev machine, and downloading one from
HuggingFace at build time is exactly the network fetch R1 forbids — so this module embeds
through the already-staged, already-local `embeddinggemma-300m` manifest (L1's Ollama
profile, see manifests/embeddinggemma-300m.yaml) via its OpenAI-compatible /v1/embeddings
endpoint instead. Zero network calls either way; the dense vector size is read from the
model at runtime rather than hardcoded, so either backend works unmodified.
"""
from __future__ import annotations

import logging
import re
import uuid
import zlib
from collections import Counter
from typing import Literal

import openai
from pydantic import BaseModel
from qdrant_client import QdrantClient, models

from core.config import SETTINGS
from core.schemas import DocumentRef, EvidenceSpan, WorkbenchError
from core.serving import REGISTRY

logger = logging.getLogger(__name__)

COLLECTION = "spans"

_EMBED_MODEL_ID = "embeddinggemma-300m"
_BATCH_SIZE = 128
_POINT_ID_NAMESPACE = uuid.UUID("c2c9f157-df9b-4c9c-9d3a-8b1a5f2f6e39")
_TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9\-]*")
# Qdrant's IDF modifier can legitimately score a term negative once it appears in more
# than half the corpus (classic BM25 behaviour) — at real-corpus scale that never
# happens for a specific equipment tag, so treating "score > this" as "no real lexical
# match" is safe and, incidentally, also excludes the zero-score padding a small
# filtered candidate set can otherwise contribute to fusion ranking.
_SPARSE_MATCH_THRESHOLD = 1e-9


class ScoredSpan(BaseModel):
    span: EvidenceSpan
    score: float
    matched_by: Literal["dense", "sparse", "both"]


# ─────────────────────────── clients (module-level singletons) ────────────────────


_qdrant: QdrantClient | None = None
_embed_client: openai.OpenAI | None = None
_embed_dim_cache: int | None = None


def _client() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=SETTINGS.qdrant_url)
    return _qdrant


def _embed_manifest():
    return REGISTRY.get(_EMBED_MODEL_ID)


def _embed_client_singleton() -> openai.OpenAI:
    global _embed_client
    if _embed_client is None:
        manifest = _embed_manifest()
        _embed_client = openai.OpenAI(base_url=manifest.base_url, api_key="EMPTY")
    return _embed_client


def _embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    manifest = _embed_manifest()
    client = _embed_client_singleton()
    try:
        response = client.embeddings.create(model=manifest.served_model_name, input=texts)
    except Exception as exc:
        raise WorkbenchError(f"embedding call to {manifest.id!r} failed: {exc}") from exc
    return [d.embedding for d in response.data]


def _embedding_dim() -> int:
    global _embed_dim_cache
    if _embed_dim_cache is None:
        _embed_dim_cache = len(_embed(["probe"])[0])
    return _embed_dim_cache


# ─────────────────────────── sparse (lexical) vectors ──────────────────────────────


def _tokenize(text: str) -> list[str]:
    """Keeps hyphenated identifiers (V-101, PSV-2204) as single tokens — the whole
    point of the lexical half is exact-tag recall, so we must not split on '-'."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _sparse_vector(text: str) -> models.SparseVector:
    """Raw term-frequency counts, keyed by a stable hash of the token. Qdrant's IDF
    modifier (configured on the collection) turns these into BM25-like weights
    server-side — no bm25/fastembed dependency needed."""
    counts = Counter(_tokenize(text))
    if not counts:
        return models.SparseVector(indices=[], values=[])
    indices = [zlib.crc32(tok.encode("utf-8")) for tok in counts]
    values = [float(c) for c in counts.values()]
    return models.SparseVector(indices=indices, values=values)


# ─────────────────────────── ids & payload mapping ─────────────────────────────────


def _point_id(span_id: str) -> str:
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, span_id))


def _payload_to_span(payload: dict) -> EvidenceSpan:
    return EvidenceSpan.model_validate(payload)


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ─────────────────────────── public API ────────────────────────────────────────────


def ensure_collection() -> None:
    """Idempotent. Dense vector (size read from the embedding model) cosine + sparse
    vector with an IDF modifier. Payload index on doc_id (keyword) and page (integer)."""
    client = _client()
    if client.collection_exists(COLLECTION):
        return

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={
            "dense": models.VectorParams(size=_embedding_dim(), distance=models.Distance.COSINE)
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    client.create_payload_index(
        COLLECTION, field_name="doc_id", field_schema=models.PayloadSchemaType.KEYWORD
    )
    client.create_payload_index(
        COLLECTION, field_name="page", field_schema=models.PayloadSchemaType.INTEGER
    )
    logger.info("collection %r created (dense=%dd cosine, sparse=idf)", COLLECTION, _embedding_dim())


def index_spans(spans: list[EvidenceSpan], doc_ref: DocumentRef) -> int:
    """Upsert. Point id = deterministic uuid5 of span_id, so re-ingesting a document
    updates in place instead of duplicating. Payload carries the full span plus
    filename and doc_kind. Batch in chunks of 128. Returns count indexed."""
    if not spans:
        return 0
    ensure_collection()
    client = _client()

    count = 0
    for batch in _chunks(spans, _BATCH_SIZE):
        dense_vectors = _embed([span.text for span in batch])
        points = [
            models.PointStruct(
                id=_point_id(span.span_id),
                vector={"dense": dense_vector, "sparse": _sparse_vector(span.text)},
                payload=span.model_dump(mode="json")
                | {"filename": doc_ref.filename, "doc_kind": doc_ref.kind.value},
            )
            for span, dense_vector in zip(batch, dense_vectors)
        ]
        client.upsert(collection_name=COLLECTION, points=points)
        count += len(points)

    logger.info("indexed %d spans for doc_id=%s", count, doc_ref.doc_id)
    return count


def search(
    query: str, *, top_k: int = 8, doc_ids: list[str] | None = None, min_score: float = 0.0
) -> list[ScoredSpan]:
    """Hybrid search with RRF fusion. Also runs the two prefetches standalone (cheap,
    same vectors) purely to label each fused hit's `matched_by` — Qdrant's fused
    response does not otherwise expose which retriever(s) contributed a point."""
    ensure_collection()
    client = _client()

    dense_vector = _embed([query])[0]
    sparse_vector = _sparse_vector(query)
    query_filter = (
        models.Filter(must=[models.FieldCondition(key="doc_id", match=models.MatchAny(any=doc_ids))])
        if doc_ids
        else None
    )
    prefetch_limit = max(top_k * 4, top_k)

    # exact=True: brute-force, not HNSW-approximate. At this project's scale (one
    # plant's manuals/SOPs/correspondence on a single Qdrant node, R11) exact search is
    # cheap and removes a real source of nondeterminism — filtered ANN search recall
    # degrades as the collection grows, which flipped close rankings under test.
    exact = models.SearchParams(exact=True)

    dense_hits = client.query_points(
        collection_name=COLLECTION,
        query=dense_vector,
        using="dense",
        limit=prefetch_limit,
        query_filter=query_filter,
        search_params=exact,
        with_payload=False,
    ).points
    # A document with no overlapping lexical terms at all still gets *some* score/rank
    # back from a small candidate set (Qdrant pads a small filtered result up to `limit`
    # rather than returning fewer points) — score_threshold keeps those non-matches out
    # of the sparse side of the fusion entirely, instead of letting RRF give a rank
    # position (and therefore fusion credit) to a document the query never lexically hit.
    sparse_hits = client.query_points(
        collection_name=COLLECTION,
        query=sparse_vector,
        using="sparse",
        limit=prefetch_limit,
        query_filter=query_filter,
        search_params=exact,
        score_threshold=_SPARSE_MATCH_THRESHOLD,
        with_payload=False,
    ).points
    dense_ids = {p.id for p in dense_hits if p.score > 0}
    sparse_ids = {p.id for p in sparse_hits}

    fused = client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(query=dense_vector, using="dense", limit=prefetch_limit, filter=query_filter, params=exact),
            models.Prefetch(
                query=sparse_vector,
                using="sparse",
                limit=prefetch_limit,
                filter=query_filter,
                params=exact,
                score_threshold=_SPARSE_MATCH_THRESHOLD,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    results: list[ScoredSpan] = []
    for point in fused.points:
        if point.score < min_score:
            continue
        in_dense, in_sparse = point.id in dense_ids, point.id in sparse_ids
        matched_by: Literal["dense", "sparse", "both"] = (
            "both" if in_dense and in_sparse else "sparse" if in_sparse else "dense"
        )
        results.append(
            ScoredSpan(span=_payload_to_span(point.payload), score=point.score, matched_by=matched_by)
        )
    return results


def get_span(span_id: str) -> EvidenceSpan:
    """Exact lookup by span_id. THIS IS THE HOT PATH FOR L7b — the renderer calls it to
    resolve every evidence_ref before writing a file. Raises WorkbenchError if missing.
    A single point retrieve by id — never a search, so never a fuzzy/nearest match."""
    client = _client()
    if not client.collection_exists(COLLECTION):
        raise WorkbenchError(f"span not found (collection {COLLECTION!r} does not exist): {span_id!r}")

    points = client.retrieve(COLLECTION, ids=[_point_id(span_id)], with_payload=True)
    if not points:
        raise WorkbenchError(f"span not found: {span_id!r}")
    return _payload_to_span(points[0].payload)


def span_exists(span_id: str) -> bool:
    client = _client()
    if not client.collection_exists(COLLECTION):
        return False
    points = client.retrieve(COLLECTION, ids=[_point_id(span_id)], with_payload=False)
    return bool(points)


def stats() -> dict:
    """{'documents': n, 'spans': n, 'collection_status': ...} — for the UI status bar."""
    client = _client()
    if not client.collection_exists(COLLECTION):
        return {"documents": 0, "spans": 0, "collection_status": "missing"}

    info = client.get_collection(COLLECTION)
    span_count = client.count(COLLECTION, exact=True).count

    doc_ids: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            COLLECTION, with_payload=["doc_id"], with_vectors=False, limit=256, offset=offset
        )
        doc_ids.update(p.payload["doc_id"] for p in points)
        if offset is None:
            break

    status = info.status.value if hasattr(info.status, "value") else str(info.status)
    return {"documents": len(doc_ids), "spans": span_count, "collection_status": status}
