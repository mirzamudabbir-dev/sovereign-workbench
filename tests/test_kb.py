"""L6 — tests for the hybrid dense+lexical Qdrant index over EvidenceSpans.

All tests need a live Qdrant (SETTINGS.qdrant_url) and a live embedding endpoint
(the embeddinggemma-300m manifest, see core/kb.py's module docstring for why that
model backs the dense half instead of the doc's originally-specified local
sentence-transformers path) — hence @pytest.mark.integration on every test in this
file. Each test scopes its assertions to its own synthetic doc_id(s) via the `doc_ids`
filter so it does not care what else lives in the shared "spans" collection.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from qdrant_client import models as qmodels

from core import kb
from core.schemas import DocKind, DocumentRef, EvidenceSpan, WorkbenchError

pytestmark = pytest.mark.integration


def _span(doc_id: str, block: int, text: str, *, page: int = 1, confidence: float = 0.95) -> EvidenceSpan:
    return EvidenceSpan(
        span_id=f"{doc_id}#p{page}.b{block}",
        doc_id=doc_id,
        page=page,
        bbox=(0.0, 0.0, 1.0, 0.1),
        text=text,
        confidence=confidence,
        extractor="native",
    )


def _doc_ref(doc_id: str, filename: str = "fixture.txt") -> DocumentRef:
    return DocumentRef(
        doc_id=doc_id,
        filename=filename,
        path=f"/tmp/{filename}",
        kind=DocKind.PLAINTEXT,
        page_count=1,
        page_images=[],
        ingested_at=datetime.now(timezone.utc),
    )


def _new_doc_id() -> str:
    return f"kbtest-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True, scope="module")
def _isolated_collection():
    """Qdrant's IDF modifier scores sparse vectors against the WHOLE collection's term
    statistics, not just the doc_ids a query filters to — so leftover points from any
    earlier manual run skew every sparse/fused score in this file (observed directly:
    the exact-tag span's sparse score flipped from strongly positive to negative purely
    because of unrelated points left over in "spans" from prior exploration). Drop and
    recreate the collection before this module's tests so IDF statistics reflect only
    the handful of spans this file itself indexes. Safe here because this is a local,
    single-tenant dev Qdrant with no real corpus loaded yet; scripts/index_corpus.py is
    the one that (re)builds the real KB, run separately, after these tests."""
    client = kb._client()
    if client.collection_exists(kb.COLLECTION):
        client.delete_collection(kb.COLLECTION)
    kb.ensure_collection()
    yield


@pytest.fixture(autouse=True, scope="module")
def _cleanup_test_docs(_isolated_collection):
    """Delete every point this module indexes once the module's tests finish, so the
    shared local "spans" collection does not grow unbounded across repeated test runs
    (an ever-larger collection is otherwise a real source of flakiness for the
    close-score assertions below, since it changes what "top-k" filtered search sees)."""
    created_doc_ids: list[str] = []
    yield created_doc_ids
    if created_doc_ids:
        kb._client().delete(
            collection_name=kb.COLLECTION,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="doc_id", match=qmodels.MatchAny(any=created_doc_ids))]
                )
            ),
        )


@pytest.fixture(scope="module")
def kb_doc(_cleanup_test_docs):
    """One indexed document with three spans: an exact-tag span, a paraphrase-able SOP
    span, and an unrelated span — enough to exercise every retrieval mode."""
    kb.ensure_collection()
    doc_id = _new_doc_id()
    _cleanup_test_docs.append(doc_id)
    spans = [
        _span(doc_id, 1, "Vessel V-101 shell thickness measured at 12.4 mm during the last inspection."),
        _span(
            doc_id,
            2,
            "Per SOP-014 clause 4.2, any vessel found below the design basis shell "
            "gauge must be withdrawn from service until repaired.",
        ),
        _span(doc_id, 3, "Correspondence: the maintenance team confirmed nozzle N-4 bolting was re-torqued."),
        # A bare tag callout for a *different* vessel — the kind of short "label" block
        # OCR emits for a drawing tag balloon (see core/ingest.py's _ingest_image). A
        # dense-only search for the bare tag "V-101" embeds closer to this short,
        # tag-shaped decoy than to the actual V-101 sentence below — see
        # test_dense_only_would_miss_tag.
        _span(doc_id, 4, "V-205"),
    ]
    ref = _doc_ref(doc_id)
    count = kb.index_spans(spans, ref)
    yield doc_id, spans, count


def test_ensure_collection_idempotent():
    kb.ensure_collection()
    kb.ensure_collection()  # must not raise or recreate
    info = kb.stats()
    assert info["collection_status"] != "missing"


def test_index_then_get_span_roundtrip(kb_doc):
    doc_id, spans, count = kb_doc
    assert count == len(spans)
    fetched = kb.get_span(spans[0].span_id)
    assert fetched.span_id == spans[0].span_id
    assert fetched.text == spans[0].text
    assert fetched.doc_id == doc_id


def test_reindex_same_doc_does_not_duplicate(kb_doc):
    doc_id, spans, _ = kb_doc
    kb.index_spans(spans, _doc_ref(doc_id))  # re-ingest, unchanged content

    count_filter = qmodels.Filter(must=[qmodels.FieldCondition(key="doc_id", match=qmodels.MatchValue(value=doc_id))])
    total = kb._client().count(collection_name=kb.COLLECTION, count_filter=count_filter, exact=True).count
    assert total == len(spans)


def test_hybrid_finds_exact_tag(kb_doc):
    doc_id, spans, _ = kb_doc
    results = kb.search("V-101", top_k=5, doc_ids=[doc_id])
    assert results, "expected at least one hit for an exact tag query"
    top_texts = [r for r in results if "V-101" in r.span.text]
    assert top_texts, "no result contained the literal tag V-101"
    assert top_texts[0].matched_by in ("sparse", "both")


def test_hybrid_finds_paraphrase(kb_doc):
    doc_id, spans, _ = kb_doc
    results = kb.search("minimum wall thickness rule for a pressure vessel", top_k=5, doc_ids=[doc_id])
    sop_span_id = spans[1].span_id
    assert any(r.span.span_id == sop_span_id for r in results), "hybrid search missed the paraphrased SOP span"


def test_dense_only_would_miss_tag(kb_doc):
    """Documents WHY hybrid exists: for the bare query "V-101", the embedding model
    ranks span 4 (a bare "V-205" tag callout — a different vessel) ABOVE span 1 (the
    actual V-101 sentence) on dense similarity alone, because a short tag-shaped decoy
    embeds closer to a bare tag query than a full sentence does. search()'s sparse half
    still nails the exact tag. Keep this test — it is the regression guard against ever
    "simplifying" this layer to dense-only."""
    doc_id, spans, _ = kb_doc
    tag_span_id = spans[0].span_id
    decoy_span_id = spans[3].span_id

    doc_filter = qmodels.Filter(must=[qmodels.FieldCondition(key="doc_id", match=qmodels.MatchValue(value=doc_id))])
    dense_vector = kb._embed(["V-101"])[0]
    dense_hits = kb._client().query_points(
        collection_name=kb.COLLECTION,
        query=dense_vector,
        using="dense",
        limit=1,
        query_filter=doc_filter,
        with_payload=True,
    ).points
    dense_top1_id = dense_hits[0].payload["span_id"] if dense_hits else None

    hybrid_results = kb.search("V-101", top_k=1, doc_ids=[doc_id])
    hybrid_top1_id = hybrid_results[0].span.span_id if hybrid_results else None

    assert hybrid_top1_id == tag_span_id, "hybrid search should rank the exact-tag span first"
    assert dense_top1_id == decoy_span_id, (
        f"test setup assumption broke: dense-only top-1 was {dense_top1_id!r}, expected the "
        f"different-tag decoy {decoy_span_id!r} to outrank the real V-101 span on dense "
        "similarity alone — re-probe the embedding model if this no longer holds"
    )


def test_filter_by_doc_ids(kb_doc, _cleanup_test_docs):
    doc_id_a, _, _ = kb_doc
    doc_id_b = _new_doc_id()
    _cleanup_test_docs.append(doc_id_b)
    other_span = _span(doc_id_b, 1, "Unrelated correspondence about a different facility entirely.")
    kb.index_spans([other_span], _doc_ref(doc_id_b))

    results = kb.search("correspondence", top_k=10, doc_ids=[doc_id_a])
    assert all(r.span.doc_id == doc_id_a for r in results)
    assert not any(r.span.span_id == other_span.span_id for r in results)


def test_get_span_missing_raises():
    with pytest.raises(WorkbenchError):
        kb.get_span("no-such-doc-ffffffff#p1.b1")


def test_get_span_never_fuzzy_matches(kb_doc):
    doc_id, spans, _ = kb_doc
    indexed_id = spans[0].span_id  # f"{doc_id}#p1.b1"
    never_indexed_id = f"{doc_id}#p1.b999"  # same doc, adjacent id, never upserted

    assert kb.span_exists(indexed_id) is True
    assert kb.span_exists(never_indexed_id) is False
    with pytest.raises(WorkbenchError):
        kb.get_span(never_indexed_id)


def test_stats_reports_counts(kb_doc):
    info = kb.stats()
    assert info["spans"] >= 3
    assert info["documents"] >= 1
    assert info["collection_status"] != "missing"
