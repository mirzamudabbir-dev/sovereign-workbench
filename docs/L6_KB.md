# L6 — KNOWLEDGE BASE

## MISSION LOCK

**Build:** a local Qdrant index over `EvidenceSpan`s with hybrid dense+lexical retrieval, so the
agent can ground answers in the organisation's own manuals, SOPs and correspondence.

**You are NOT building:** ingestion/OCR (L3 hands you spans), the agent (L4), or any generation.
Retrieval returns spans. It never returns prose.

**Serves:** R10 (grounded in org's own manuals/SOPs/correspondence via local KB connector),
and the `kb.search` tool of R6.

**Files You Own:**
```
core/kb.py
scripts/index_corpus.py
tests/test_kb.py
```

---

## The one design decision

**Hybrid retrieval is mandatory, not a nice-to-have.** The corpus is full of equipment tags
(`V-101`), instrument numbers (`PSV-2204`), line numbers, clause references and standard codes.
Dense embeddings reliably miss exact identifiers; lexical search reliably misses paraphrased
SOP intent. A query like *"what does the SOP say about minimum thickness for V-101"* needs both
halves simultaneously.

Qdrant does dense + sparse natively in one collection with server-side fusion, so this is
configuration, not code. Use it.

```
EvidenceSpan ──┬──► BGE-M3 dense vector (1024d, cosine)
               └──► BM25 sparse vector (Qdrant IDF modifier)
                         │
                    Qdrant Query API, RRF prefetch fusion
                         │
                    list[ScoredSpan]
```

**Do not add a reranker, ColPali, ColQwen, or visual retrieval.** They are genuinely better on
dense tables and they are an optimization the PS does not ask for. Note them in `PROGRESS.md`
as post-demo work.

---

## `core/kb.py` — required API

```python
"""L6 — local hybrid retrieval over EvidenceSpans. Returns spans, never prose."""

COLLECTION = "spans"

class ScoredSpan(BaseModel):
    span: EvidenceSpan
    score: float
    matched_by: Literal["dense", "sparse", "both"]


def ensure_collection() -> None:
    """Idempotent. Dense vector 1024d cosine + sparse vector with IDF modifier.
    Payload index on doc_id (keyword) and page (integer) for filtered search."""


def index_spans(spans: list[EvidenceSpan], doc_ref: DocumentRef) -> int:
    """Upsert. Point id = deterministic uuid5 of span_id, so re-ingesting a document
    updates in place instead of duplicating. Payload carries the full span plus
    filename and doc_kind. Batch in chunks of 128. Returns count indexed."""


def search(query: str, *, top_k: int = 8, doc_ids: list[str] | None = None,
           min_score: float = 0.0) -> list[ScoredSpan]:
    """Hybrid search with RRF fusion.

    client.query_points(
        collection_name=COLLECTION,
        prefetch=[Prefetch(query=dense_vec, using="dense", limit=top_k * 4),
                  Prefetch(query=sparse_vec, using="sparse", limit=top_k * 4)],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        query_filter=<doc_ids filter or None>,
        with_payload=True,
    )
    """


def get_span(span_id: str) -> EvidenceSpan:
    """Exact lookup by span_id. THIS IS THE HOT PATH FOR L7b — the renderer calls it to
    resolve every evidence_ref before writing a file. Must raise WorkbenchError if missing."""


def span_exists(span_id: str) -> bool: ...

def stats() -> dict:
    """{'documents': n, 'spans': n, 'collection_status': ...} — for the UI status bar."""
```

Embedding model: `SentenceTransformer(SETTINGS.embedding_model_path)` (`BAAI/bge-m3`), loaded
once at module import, `normalize_embeddings=True`. Load from the local path staged by L0 —
**never a HuggingFace model id at runtime**, that is a network call and an R1 violation.

Sparse vectors: use `qdrant_client` BM25 support via `models.SparseVector`, or Qdrant's
built-in IDF modifier. Either is fine; pick one and document it.

---

## `scripts/index_corpus.py`

The "local knowledge base connector" of R10. A CLI that walks a directory of the organisation's
own documents and indexes them:

```bash
python scripts/index_corpus.py --dir /srv/plant-docs --recursive
```

For each file: `core.ingest.ingest()` → `index_spans()`. Progress bar, skip-if-unchanged via
file mtime + size recorded in a small SQLite table, `--force` to reindex. Print a summary table
at the end. This is what you run once before the demo to load the SOP corpus.

---

## `get_span` is the contract that makes grounding real

L7b will call `get_span(evidence_ref)` for **every** field before rendering a deliverable. If it
raises, the render fails closed. That means:
- `get_span` must be fast (single point retrieve by id) — do not implement it as a search.
- It must never return a fuzzy or nearest match. Exact id or `WorkbenchError`.

Write `test_get_span_never_fuzzy_matches` to lock this in.

---

## Tests — `tests/test_kb.py`

```python
@pytest.mark.integration                 # needs Qdrant on :6333
def test_ensure_collection_idempotent()
def test_index_then_get_span_roundtrip()
def test_reindex_same_doc_does_not_duplicate()
def test_hybrid_finds_exact_tag()        # index "V-101 shell thickness"; query "V-101"
def test_hybrid_finds_paraphrase()       # query "minimum wall thickness rule" hits the SOP span
def test_dense_only_would_miss_tag()     # documents WHY hybrid exists — assert & keep
def test_filter_by_doc_ids()
def test_get_span_missing_raises()
def test_get_span_never_fuzzy_matches()
def test_stats_reports_counts()
```

`test_hybrid_finds_exact_tag` and `test_dense_only_would_miss_tag` together are your
justification if a judge asks why you didn't just use embeddings.

---

## Definition of Done

```bash
pytest tests/test_kb.py -v
python scripts/index_corpus.py --dir tests/fixtures --recursive
python -c "
from core.kb import search, stats
print(stats())
for s in search('V-101 minimum thickness', top_k=3):
    print(round(s.score,3), s.matched_by, s.span.span_id, s.span.text[:70])
"
```
Must return ≥1 result whose text contains the literal tag, with `matched_by` showing sparse or
both — proving the lexical half is live.

## Drift tripwires

- ❌ Adding a cross-encoder reranker, ColPali/ColQwen, or visual retrieval.
- ❌ GraphRAG, knowledge graphs, entity extraction.
- ❌ Swapping Qdrant for Chroma/FAISS/pgvector mid-build.
- ❌ Returning generated text from `search()`. Spans only — generation belongs to L4.
- ❌ Loading the embedding model by HF id at runtime (network call → breaks R1).
- ❌ Chunking spans further, or merging them. L3 decided the granularity; respect it.

## Session exit

`PROGRESS.md`: collection size after indexing fixtures, embedding load time, whether sparse
vectors use client-side BM25 or Qdrant IDF.
`## Next action: L7b — core/render.py (RenderPlan → docx/pptx/xlsx)`
