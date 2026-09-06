"""L3 — tests for document classification and ingestion.

Fixtures live in tests/fixtures/: a born-digital PDF, an image-only ("scanned") PDF whose
single page contains the literal tag V-101, and a simple engineering-drawing PNG containing
the tag PSV-2204. Non-integration tests never call a live model — they exercise classify(),
the Docling native path (offline once its layout model is cached), and _blocks_to_spans()
directly with a synthetic _OcrPage. Only test_scanned_pdf_extracts_known_tag needs a live
OCR model server and is marked accordingly.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.ingest import (
    _OcrBlock,
    _OcrPage,
    _blocks_to_spans,
    classify,
    crop_span,
    ingest,
    page_image_path,
)
from core.schemas import DocKind

FIXTURES = Path(__file__).parent / "fixtures"
NATIVE_PDF = FIXTURES / "inspection_native.pdf"
SCANNED_PDF = FIXTURES / "inspection_scanned.pdf"
DRAWING_IMAGE = FIXTURES / "drawing_psv2204.png"

_SPAN_ID_RE = re.compile(r"^[a-z0-9-]+#p\d+\.b\d+$")


def test_classify_native_pdf():
    assert classify(NATIVE_PDF) == DocKind.NATIVE_PDF


def test_classify_scanned_pdf():
    assert classify(SCANNED_PDF) == DocKind.SCANNED_PDF


def test_classify_image():
    assert classify(DRAWING_IMAGE) == DocKind.IMAGE


def test_bboxes_are_normalised():
    ref, spans = ingest(NATIVE_PDF)
    assert len(spans) > 0
    for span in spans:
        x0, y0, x1, y1 = span.bbox
        assert 0.0 <= x0 <= 1.0
        assert 0.0 <= y0 <= 1.0
        assert 0.0 <= x1 <= 1.0
        assert 0.0 <= y1 <= 1.0
        assert x0 < x1
        assert y0 < y1


def test_span_ids_are_unique_and_wellformed():
    ref, spans = ingest(NATIVE_PDF)
    ids = [s.span_id for s in spans]
    assert len(ids) == len(set(ids))
    for span_id in ids:
        assert _SPAN_ID_RE.match(span_id), span_id
        assert span_id.startswith(ref.doc_id + "#")


def test_page_images_rendered_for_every_page():
    ref, spans = ingest(NATIVE_PDF)
    assert ref.page_count == 2
    assert len(ref.page_images) == ref.page_count
    for i, image_path in enumerate(ref.page_images, start=1):
        p = Path(image_path)
        assert p.is_file()
        assert p == page_image_path(ref.doc_id, i)
        assert p.stat().st_size > 0


def test_low_confidence_marks_needs_review():
    # Pure unit test — no live model. ocr_review_threshold is 0.75 (config.yaml).
    ocr_page = _OcrPage(
        blocks=[
            _OcrBlock(text="clear text", bbox=(0.1, 0.1, 0.5, 0.2), kind="paragraph", confidence=0.95),
            _OcrBlock(text="scribbled note", bbox=(0.1, 0.3, 0.5, 0.4), kind="handwriting", confidence=0.4),
        ]
    )
    spans = _blocks_to_spans("doc-test", 1, ocr_page, {}, image_size=(1000, 1000))
    assert len(spans) == 2
    by_text = {s.text: s for s in spans}
    assert by_text["clear text"].needs_review is False
    assert by_text["scribbled note"].needs_review is True
    assert by_text["scribbled note"].confidence == pytest.approx(0.4)


def test_blocks_to_spans_normalises_pixel_coordinates():
    # Regression test for a real finding on this dev profile: the local OCR model
    # sometimes returns raw pixel coordinates despite the prompt's "0..1" instruction.
    ocr_page = _OcrPage(
        blocks=[_OcrBlock(text="pixel box", bbox=(100.0, 200.0, 300.0, 250.0), kind="label", confidence=0.9)]
    )
    spans = _blocks_to_spans("doc-test", 1, ocr_page, {}, image_size=(1000, 500))
    assert len(spans) == 1
    x0, y0, x1, y1 = spans[0].bbox
    assert x0 == pytest.approx(0.1)
    assert x1 == pytest.approx(0.3)
    assert y0 == pytest.approx(0.4)
    assert y1 == pytest.approx(0.5)


def test_crop_span_produces_nonempty_image():
    ref, spans = ingest(NATIVE_PDF)
    crop_path = crop_span(spans[0])
    assert crop_path.is_file()
    assert crop_path.stat().st_size > 0


@pytest.mark.integration
def test_scanned_pdf_extracts_known_tag():
    """The regression test protecting against OCR 'correction': V-101 must survive verbatim."""
    ref, spans = ingest(SCANNED_PDF)
    assert ref.kind == DocKind.SCANNED_PDF
    assert len(spans) > 0
    assert any(span.extractor == "paddleocr-vl" for span in spans)
    all_text = " ".join(s.text for s in spans)
    assert "V-101" in all_text
