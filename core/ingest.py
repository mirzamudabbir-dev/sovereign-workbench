"""L3 — file → DocumentRef + EvidenceSpans. Every span carries a bbox."""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from PIL import Image
from pydantic import BaseModel

from core.config import SETTINGS
from core.schemas import DocKind, DocumentRef, EvidenceSpan, WorkbenchError

logger = logging.getLogger(__name__)

_SCANNED_THRESHOLD_CHARS_PER_PAGE = 100
_RENDER_DPI = 150
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
_OFFICE_SUFFIXES = {".docx", ".xlsx", ".pptx"}
_PLAINTEXT_SUFFIXES = {".txt", ".md"}

# PaddleOCR-VL prompt — verbatim from docs/L3_INGESTION.md. The final rule is the one that
# matters: an OCR model that "helpfully" corrects a tag number silently corrupts every
# downstream citation.
_OCR_PROMPT = """Extract every text region from this document page.
For each region return: the text, a normalised bounding box [x0,y0,x1,y1] with values in
0..1 relative to the full page, a kind, and a confidence in 0..1.

Rules:
- Preserve engineering tag numbers exactly as written (e.g. V-101, PSV-2204, 10"-P-1502-A1A).
- For tables, emit one region per row, text as pipe-separated cells.
- If a region is handwritten, set kind="handwriting" and confidence to your true confidence.
- Do not summarise, translate, correct spelling, or infer missing text."""


class _OcrBlock(BaseModel):
    text: str
    bbox: tuple[float, float, float, float]  # normalised
    kind: Literal["paragraph", "table", "heading", "handwriting", "figure", "label"]
    confidence: float


class _OcrPage(BaseModel):
    blocks: list[_OcrBlock]


# ─────────────────────────── classification ────────────────────────────────────


def classify(path: Path) -> DocKind:
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in _IMAGE_SUFFIXES:
        return DocKind.IMAGE
    if suffix in _OFFICE_SUFFIXES:
        return DocKind.OFFICE
    if suffix in _PLAINTEXT_SUFFIXES:
        return DocKind.PLAINTEXT
    if suffix != ".pdf":
        raise WorkbenchError(f"unsupported file type: {suffix!r} ({path})")

    pdf = fitz.open(path)
    try:
        page_count = pdf.page_count
        if page_count == 0:
            raise WorkbenchError(f"PDF has no pages: {path}")
        char_counts = [len(page.get_text()) for page in pdf]
    finally:
        pdf.close()

    mean_chars = sum(char_counts) / page_count
    logger.info("classify: %s mean_chars_per_page=%.1f pages=%d", path, mean_chars, page_count)
    return DocKind.SCANNED_PDF if mean_chars < _SCANNED_THRESHOLD_CHARS_PER_PAGE else DocKind.NATIVE_PDF


def _make_doc_id(path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "doc"
    return f"{slug}-{uuid.uuid4().hex[:4]}"


# ─────────────────────────── page images ────────────────────────────────────────


def page_image_path(doc_id: str, page: int) -> Path:
    return SETTINGS.paths.page_images / f"{doc_id}_p{page:03d}.png"


def _render_pdf_pages(pdf: fitz.Document, doc_id: str) -> list[Path]:
    SETTINGS.paths.page_images.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(pdf.page_count):
        page_no = i + 1
        pix = pdf[i].get_pixmap(dpi=_RENDER_DPI)
        out_path = page_image_path(doc_id, page_no)
        pix.save(str(out_path))
        paths.append(out_path)
    return paths


def _render_image_as_page(path: Path, doc_id: str) -> Path:
    SETTINGS.paths.page_images.mkdir(parents=True, exist_ok=True)
    out_path = page_image_path(doc_id, 1)
    with Image.open(path) as img:
        img.convert("RGB").save(out_path, format="PNG")
    return out_path


def crop_span(span: EvidenceSpan) -> Path:
    """Crop the span's bbox out of its page image. Used by the UI evidence panel and to feed
    a specific region back to a vision model. Cache under page_images/crops/."""
    src = page_image_path(span.doc_id, span.page)
    if not src.is_file():
        raise WorkbenchError(f"page image not found for span {span.span_id}: {src}")

    crops_dir = SETTINGS.paths.page_images / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    safe_id = span.span_id.replace("#", "_").replace(".", "_")
    out_path = crops_dir / f"{safe_id}.png"
    if out_path.is_file():
        return out_path

    with Image.open(src) as img:
        w, h = img.size
        x0, y0, x1, y1 = span.bbox
        left = max(0, min(w - 1, int(x0 * w)))
        top = max(0, min(h - 1, int(y0 * h)))
        right = max(left + 1, min(w, int(x1 * w)))
        bottom = max(top + 1, min(h, int(y1 * h)))
        img.crop((left, top, right, bottom)).convert("RGB").save(out_path, format="PNG")
    return out_path


# ─────────────────────────── entry point ─────────────────────────────────────────


def ingest(path: Path, doc_id: str | None = None) -> tuple[DocumentRef, list[EvidenceSpan]]:
    """Single entry point for the whole layer. Dispatches on classify().
    Always renders page images to SETTINGS.paths.page_images (needed by the UI evidence
    panel and by PaddleOCR-VL), at 150 DPI, named {doc_id}_p{page:03d}.png."""
    path = Path(path)
    if not path.is_file():
        raise WorkbenchError(f"no such file: {path}")

    doc_id = doc_id or _make_doc_id(path)
    kind = classify(path)

    if kind in (DocKind.NATIVE_PDF, DocKind.SCANNED_PDF):
        pdf = fitz.open(path)
        try:
            page_count = pdf.page_count
            page_images = _render_pdf_pages(pdf, doc_id)
        finally:
            pdf.close()
    elif kind == DocKind.IMAGE:
        page_count = 1
        page_images = [_render_image_as_page(path, doc_id)]
    elif kind in (DocKind.PLAINTEXT, DocKind.OFFICE):
        # No page geometry to rasterise for either kind (plaintext has none; office rendering
        # would need a document-to-PDF rasteriser, out of scope for this session — see
        # PROGRESS.md). Spans are still extracted correctly below; only the DocumentRef's
        # page_images bookkeeping is approximate for these two kinds.
        page_count = 1
        page_images = []
    else:
        raise WorkbenchError(f"unhandled doc kind: {kind}")

    ref = DocumentRef(
        doc_id=doc_id,
        filename=path.name,
        path=str(path.resolve()),
        kind=kind,
        page_count=page_count,
        page_images=[str(p) for p in page_images],
        ingested_at=datetime.now(timezone.utc),
    )

    if kind == DocKind.NATIVE_PDF:
        spans = _ingest_native(path, doc_id, ref)
    elif kind == DocKind.SCANNED_PDF:
        spans = _ingest_scanned(path, doc_id, ref)
    elif kind == DocKind.IMAGE:
        spans = _ingest_image(path, doc_id, ref)
    elif kind == DocKind.PLAINTEXT:
        spans = _ingest_plaintext(path, doc_id, ref)
    elif kind == DocKind.OFFICE:
        spans = _ingest_native(path, doc_id, ref)  # Docling handles docx/xlsx/pptx too

    return ref, spans


# ─────────────────────────── native (Docling) ─────────────────────────────────────


def _ingest_native(path: Path, doc_id: str, ref: DocumentRef) -> list[EvidenceSpan]:
    """Docling. Map each text item to a span. Docling gives bboxes in page coordinates —
    normalise to [0,1] against the page size. extractor='docling', confidence=0.99."""
    # do_ocr=False is load-bearing, not an optimisation: Docling's default pipeline runs
    # EasyOCR internally, which is on the forbidden list (docs/CLAUDE.md) and would silently
    # download model weights over the network on first use. Native/office documents already
    # have a text layer — OCR must never run on this path.
    pipeline_options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    result = converter.convert(str(path))
    doc = result.document
    page_sizes = {p.page_no: p.size for p in doc.pages.values()}

    spans: list[EvidenceSpan] = []
    block_counters: dict[int, int] = {}
    for item in doc.texts:
        text = (item.text or "").strip()
        if not text:
            continue
        for prov in item.prov:
            size = page_sizes.get(prov.page_no)
            if size is None:
                continue
            box = prov.bbox.to_top_left_origin(size.height).normalized(size)
            x0, x1 = sorted((max(0.0, min(1.0, box.l)), max(0.0, min(1.0, box.r))))
            y0, y1 = sorted((max(0.0, min(1.0, box.t)), max(0.0, min(1.0, box.b))))
            if x1 <= x0 or y1 <= y0:
                continue
            block_counters[prov.page_no] = block_counters.get(prov.page_no, 0) + 1
            idx = block_counters[prov.page_no]
            spans.append(
                EvidenceSpan(
                    span_id=f"{doc_id}#p{prov.page_no}.b{idx}",
                    doc_id=doc_id,
                    page=prov.page_no,
                    bbox=(x0, y0, x1, y1),
                    text=text,
                    confidence=0.99,
                    extractor="docling",
                    needs_review=False,
                )
            )
    return spans


# ─────────────────────────── scanned / image (PaddleOCR-VL) ───────────────────────


def _call_ocr_page(image_path: Path) -> _OcrPage:
    from core.serving import complete_structured  # deferred: avoid an import cycle at module load

    async def _call() -> _OcrPage:
        result = await complete_structured(
            SETTINGS.ocr_model_id,
            [{"role": "user", "content": _OCR_PROMPT}],
            _OcrPage,
            images=[image_path],
        )
        return result  # type: ignore[return-value]

    return asyncio.run(_call())


def _coerce_to_normalised(
    bbox: tuple[float, float, float, float], image_size: tuple[int, int]
) -> tuple[float, float, float, float]:
    """Some vision-LLM OCR backends (this project's local dev profile substitutes a general
    vision model for real PaddleOCR-VL — see PROGRESS.md) ignore the prompt's "0..1 normalised"
    instruction and return raw pixel coordinates instead, sized to the page image we sent them.
    This is a deterministic unit conversion against a bbox the model already returned — it never
    touches the extracted *text*, so it isn't the kind of LLM "cleanup" this layer forbids.
    """
    x0, y0, x1, y1 = bbox
    if max(abs(x0), abs(y0), abs(x1), abs(y1)) > 1.001:
        w, h = image_size
        x0, x1 = x0 / w, x1 / w
        y0, y1 = y0 / h, y1 / h
    return x0, y0, x1, y1


def _blocks_to_spans(
    doc_id: str,
    page_no: int,
    ocr_page: _OcrPage,
    block_counters: dict[int, int],
    image_size: tuple[int, int],
) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    for block in ocr_page.blocks:
        text = block.text.strip()
        if not text:
            continue
        bx0, by0, bx1, by1 = _coerce_to_normalised(block.bbox, image_size)
        x0, x1 = sorted((max(0.0, min(1.0, bx0)), max(0.0, min(1.0, bx1))))
        y0, y1 = sorted((max(0.0, min(1.0, by0)), max(0.0, min(1.0, by1))))
        if x1 <= x0 or y1 <= y0:
            logger.warning(
                "dropping OCR block with degenerate bbox on %s p%d: %r", doc_id, page_no, block.bbox
            )
            continue
        block_counters[page_no] = block_counters.get(page_no, 0) + 1
        idx = block_counters[page_no]
        confidence = max(0.0, min(1.0, block.confidence))
        spans.append(
            EvidenceSpan(
                span_id=f"{doc_id}#p{page_no}.b{idx}",
                doc_id=doc_id,
                page=page_no,
                bbox=(x0, y0, x1, y1),
                text=text,
                confidence=confidence,
                extractor="paddleocr-vl",
                needs_review=confidence < SETTINGS.agent.ocr_review_threshold,
            )
        )
    return spans


def _ingest_scanned(path: Path, doc_id: str, ref: DocumentRef) -> list[EvidenceSpan]:
    """For each rendered page PNG, call PaddleOCR-VL via core.serving.complete_structured
    with the _OcrPage schema below. extractor='paddleocr-vl'."""
    spans: list[EvidenceSpan] = []
    block_counters: dict[int, int] = {}
    for page_no, image_path in enumerate(ref.page_images, start=1):
        image_path = Path(image_path)
        with Image.open(image_path) as img:
            image_size = img.size
        t0 = time.monotonic()
        ocr_page = _call_ocr_page(image_path)
        latency_ms = (time.monotonic() - t0) * 1000
        logger.info("ocr page=%d doc_id=%s blocks=%d latency_ms=%.1f", page_no, doc_id, len(ocr_page.blocks), latency_ms)
        spans.extend(_blocks_to_spans(doc_id, page_no, ocr_page, block_counters, image_size))
    return spans


def _ingest_image(path: Path, doc_id: str, ref: DocumentRef) -> list[EvidenceSpan]:
    """Engineering drawings, photos: IMAGE kind, handled directly by PaddleOCR-VL. Tag
    callouts on a drawing come back with kind='label' — chosen by the model, not forced here;
    'label' is simply one of _OcrBlock.kind's allowed values."""
    block_counters: dict[int, int] = {}
    image_path = Path(ref.page_images[0])
    with Image.open(image_path) as img:
        image_size = img.size
    t0 = time.monotonic()
    ocr_page = _call_ocr_page(image_path)
    latency_ms = (time.monotonic() - t0) * 1000
    logger.info("ocr page=1 doc_id=%s blocks=%d latency_ms=%.1f", doc_id, len(ocr_page.blocks), latency_ms)
    return _blocks_to_spans(doc_id, 1, ocr_page, block_counters, image_size)


# ─────────────────────────── plaintext ───────────────────────────────────────────


def _ingest_plaintext(path: Path, doc_id: str, ref: DocumentRef) -> list[EvidenceSpan]:
    """Trivial single span per paragraph. No real page geometry exists, so each paragraph
    gets an equal vertical slice of a synthetic single page — ordered, non-degenerate, and
    good enough for citation; there is nothing to OCR or lay out."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    n = len(paragraphs)
    spans: list[EvidenceSpan] = []
    for i, para in enumerate(paragraphs):
        spans.append(
            EvidenceSpan(
                span_id=f"{doc_id}#p1.b{i + 1}",
                doc_id=doc_id,
                page=1,
                bbox=(0.0, i / n, 1.0, (i + 1) / n),
                text=para,
                confidence=0.99,
                extractor="native",
                needs_review=False,
            )
        )
    return spans
