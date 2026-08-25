# L3 — DOCUMENT INGESTION

## MISSION LOCK

**Build:** the pipeline that turns any uploaded file into `DocumentRef` + a list of
`EvidenceSpan` with real bounding boxes, using Docling for born-digital PDFs and **PaddleOCR-VL**
for scans, photographs and engineering drawings.

**You are NOT building:** embeddings, vector storage or retrieval (L6), the agent (L4), or the
renderer (L7b). You produce spans; L6 indexes them; L7b cites them.

**Serves:** R8 (scanned PDFs, handwriting, drawings, photos via on-device OCR/vision), R15.

**Files You Own:**
```
core/ingest.py
tests/test_ingest.py
tests/fixtures/          (sample native PDF, scanned PDF, drawing image)
```

---

## Why two extractors, not one

Routing by document kind is the whole design. Born-digital PDFs already have a text layer with
exact coordinates — running OCR over them destroys accuracy and wastes GPU. Scans have no text
layer at all. So:

```
classify(file)
  ├─ NATIVE_PDF  → Docling         (text layer + layout model, native bboxes)
  ├─ SCANNED_PDF → render pages → PaddleOCR-VL per page  (:8004)
  ├─ IMAGE       → PaddleOCR-VL directly
  ├─ OFFICE      → Docling
  └─ PLAINTEXT   → trivial single span per paragraph
```

Classification rule for PDFs (implement exactly this, it is deterministic and testable):
> Extract text with PyMuPDF. If mean extractable characters per page **< 100**, it is
> `SCANNED_PDF`. Otherwise `NATIVE_PDF`. Record the measured value in the log.

---

## `core/ingest.py` — required API

```python
"""L3 — file → DocumentRef + EvidenceSpans. Every span carries a bbox."""

def classify(path: Path) -> DocKind: ...


def ingest(path: Path, doc_id: str | None = None) -> tuple[DocumentRef, list[EvidenceSpan]]:
    """Single entry point for the whole layer. Dispatches on classify().
    Always renders page images to SETTINGS.paths.page_images (needed by the UI evidence
    panel and by PaddleOCR-VL), at 150 DPI, named {doc_id}_p{page:03d}.png."""


def _ingest_native(path, doc_id, ref) -> list[EvidenceSpan]:
    """Docling. Map each text item to a span. Docling gives bboxes in page coordinates —
    normalise to [0,1] against the page size. extractor='docling', confidence=0.99."""


def _ingest_scanned(path, doc_id, ref) -> list[EvidenceSpan]:
    """For each rendered page PNG, call PaddleOCR-VL via core.serving.complete_structured
    with the _OcrPage schema below. extractor='paddleocr-vl'."""


class _OcrBlock(BaseModel):
    text: str
    bbox: tuple[float, float, float, float]   # normalised
    kind: Literal["paragraph", "table", "heading", "handwriting", "figure", "label"]
    confidence: float


class _OcrPage(BaseModel):
    blocks: list[_OcrBlock]


def page_image_path(doc_id: str, page: int) -> Path: ...

def crop_span(span: EvidenceSpan) -> Path:
    """Crop the span's bbox out of its page image. Used by the UI evidence panel and to feed
    a specific region back to a vision model. Cache under page_images/crops/."""
```

### The PaddleOCR-VL call

`core/serving.py` handles transport. You own the prompt:

```
Extract every text region from this document page.
For each region return: the text, a normalised bounding box [x0,y0,x1,y1] with values in
0..1 relative to the full page, a kind, and a confidence in 0..1.

Rules:
- Preserve engineering tag numbers exactly as written (e.g. V-101, PSV-2204, 10"-P-1502-A1A).
- For tables, emit one region per row, text as pipe-separated cells.
- If a region is handwritten, set kind="handwriting" and confidence to your true confidence.
- Do not summarise, translate, correct spelling, or infer missing text.
```

The last line matters. An OCR model that "helpfully" corrects a tag number silently corrupts
evidence, and every downstream citation inherits the corruption.

### Handwriting handling — scope honestly

Handwriting is the weakest area of every open OCR model. Do not pretend otherwise.

```python
if block.confidence < SETTINGS.agent.ocr_review_threshold:   # 0.75
    span.needs_review = True
```

`needs_review` spans are still indexed and still citable, but the UI marks them amber and the
renderer (L7b) refuses to place a `needs_review` span into a numeric field without human
confirmation. **Do not build a handwriting-specific model, do not fine-tune, do not claim solved
extraction.** Assisted transcription with confidence flags is the deliverable.

### Engineering drawings

Treat as `IMAGE` → PaddleOCR-VL with `kind="label"` for tag callouts. That satisfies R8 and R15.

> **Explicitly out of scope:** P&ID symbol detection, line tracing, and graph/topology
> extraction. It is excellent work and it is not in the PS. If you have spare time it is a
> post-demo item, recorded in `PROGRESS.md`, not built here.

---

## Tests — `tests/test_ingest.py`

```python
def test_classify_native_pdf()
def test_classify_scanned_pdf()             # fixture: image-only PDF
def test_classify_image()
def test_bboxes_are_normalised()            # all coords in [0,1], x0<x1, y0<y1
def test_span_ids_are_unique_and_wellformed()   # matches {doc}#p{n}.b{n}
def test_page_images_rendered_for_every_page()
def test_low_confidence_marks_needs_review()
def test_crop_span_produces_nonempty_image()

@pytest.mark.integration
def test_scanned_pdf_extracts_known_tag()   # fixture contains "V-101"; assert it survives verbatim
```

`test_scanned_pdf_extracts_known_tag` is the regression test that protects against the OCR model
"correcting" identifiers. Keep a real scanned fixture in the repo.

---

## Definition of Done

```bash
pytest tests/test_ingest.py -v
python -c "
from pathlib import Path; from core.ingest import ingest
ref, spans = ingest(Path('tests/fixtures/inspection_scanned.pdf'))
print(ref.kind, ref.page_count, len(spans))
print(spans[0].model_dump_json(indent=2))
"
```
Must print `scanned_pdf`, a page count, a non-zero span count, and a first span with a
normalised bbox and `extractor='paddleocr-vl'`.

## Drift tripwires

- ❌ Building P&ID symbol detection or a drawing graph index.
- ❌ Fine-tuning anything for handwriting.
- ❌ Adding Tesseract, EasyOCR, Surya, or MinerU. Docling + PaddleOCR-VL is the whole set.
- ❌ Emitting a span without a bbox, or with pixel coordinates instead of normalised.
- ❌ Chunking, embedding or storing vectors. That is L6.
- ❌ Post-processing OCR text with a second LLM "cleanup" pass — that is how provenance dies.

## Session exit

`PROGRESS.md`: measured chars/page threshold behaviour on your fixtures, OCR latency per page,
observed handwriting confidence range.
`## Next action: L6 — core/kb.py (Qdrant hybrid index over EvidenceSpans)`
