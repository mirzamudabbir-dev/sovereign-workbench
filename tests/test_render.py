"""L7b — tests for validate_plan()/render() and the three private renderers.

This layer explicitly does not own retrieval (see docs/L7B_RENDERER.md's MISSION LOCK),
so these tests never touch a live Qdrant. Instead this module patches core.render.get_span
(the one name render.py imports from core.kb) with an in-memory lookup over a small fixture
set of real EvidenceSpan objects, at IMPORT TIME — not via a pytest fixture — because the
Definition of Done runs sample_plan() from a bare `python -c` script outside of pytest
entirely (`from tests.test_render import sample_plan`), so the patch has to already be in
effect the moment this module is imported, pytest or not.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

import core.render as render_module
from core.config import SETTINGS
from core.render import EvidenceResolutionError, file_sha256, render, validate_plan
from core.schemas import EvidenceSpan, Finding, GroundedValue, RenderPlan, WorkbenchError

# ─────────────────────────── fake KB (import-time patch, see module docstring) ────

_FIXTURE_SPANS: dict[str, EvidenceSpan] = {
    "insp-2214#p7.b1": EvidenceSpan(
        span_id="insp-2214#p7.b1", doc_id="insp-2214", page=7, bbox=(0.1, 0.1, 0.6, 0.2),
        text="Vessel V-101 shell thickness measured at 12.4 mm during the annual inspection.",
        confidence=0.98, extractor="docling", needs_review=False,
    ),
    "insp-2214#p2.b1": EvidenceSpan(
        span_id="insp-2214#p2.b1", doc_id="insp-2214", page=2, bbox=(0.1, 0.3, 0.6, 0.4),
        text="Minimum required thickness is 10.5 mm per the original design specification.",
        confidence=0.99, extractor="docling", needs_review=False,
    ),
    "corr-0091#p1.b1": EvidenceSpan(
        span_id="corr-0091#p1.b1", doc_id="corr-0091", page=1, bbox=(0.1, 0.1, 0.6, 0.2),
        text="Maintenance confirmed nozzle N-4 bolting was re-torqued to spec.",
        confidence=0.95, extractor="native", needs_review=False,
    ),
    "insp-2214#p7.b2": EvidenceSpan(
        span_id="insp-2214#p7.b2", doc_id="insp-2214", page=7, bbox=(0.1, 0.4, 0.6, 0.5),
        text="Head thickness (handwritten note): approximately 11.8 mm.",
        confidence=0.55, extractor="paddleocr-vl", needs_review=True,
    ),
}


def _fake_get_span(span_id: str) -> EvidenceSpan:
    span = _FIXTURE_SPANS.get(span_id)
    if span is None:
        raise WorkbenchError(f"no such span (fixture KB): {span_id!r}")
    return span


render_module.get_span = _fake_get_span


# ─────────────────────────── sample_plan (imported directly by the DoD script) ────


def sample_plan(output_format: str = "docx") -> RenderPlan:
    template_id = {"docx": "approval_note_v1", "pptx": "board_deck_v1", "xlsx": "calc_sheet_v1"}[output_format]
    return RenderPlan(
        template_id=template_id,
        output_format=output_format,
        title="V-101 Annual Inspection Approval Note",
        fields={
            "equipment_tag": GroundedValue(value="V-101", evidence_ref="insp-2214#p7.b1"),
            "shell_thickness": GroundedValue(value=12.4, unit="mm", evidence_ref="insp-2214#p7.b1"),
            "min_required_thickness": GroundedValue(value=10.5, unit="mm", evidence_ref="insp-2214#p2.b1"),
            "average_thickness": GroundedValue(
                value=12.35, unit="mm",
                computed_from=["insp-2214#p7.b1", "insp-2214#p2.b1"],
                calculation="(12.4 + 10.5) / 2 = 11.45\nindependent re-derivation: agrees",
            ),
        },
        findings=[
            Finding(
                title="Shell thickness within tolerance",
                detail="Measured shell thickness exceeds the minimum required thickness.",
                severity="info",
                evidence_refs=["insp-2214#p7.b1", "insp-2214#p2.b1"],
            ),
            Finding(
                title="Nozzle bolting re-torqued",
                detail="Maintenance correspondence confirms N-4 bolting was re-torqued to spec.",
                severity="observation",
                evidence_refs=["corr-0091#p1.b1"],
            ),
        ],
        recommendation="Approve continued service; re-inspect in 24 months.",
    )


def _unique_task_id(name: str) -> str:
    return f"t-test-{name}-{int(time.monotonic() * 1000) % 1_000_000}"


# ─────────────────────────── validate_plan ─────────────────────────────────────────


def test_validate_rejects_field_without_evidence_ref():
    plan = sample_plan("docx")
    plan.fields["orphan"] = GroundedValue(value="no evidence here")
    with pytest.raises(EvidenceResolutionError, match="orphan"):
        validate_plan(plan)


def test_validate_rejects_unresolvable_span():
    plan = sample_plan("docx")
    plan.fields["bad_ref"] = GroundedValue(value=1, evidence_ref="bogus#p1.b1")
    with pytest.raises(EvidenceResolutionError, match="bogus#p1.b1"):
        validate_plan(plan)


def test_validate_rejects_needs_review_span_in_numeric_field():
    plan = sample_plan("docx")
    plan.fields["head_thickness"] = GroundedValue(value=11.8, unit="mm", evidence_ref="insp-2214#p7.b2")
    with pytest.raises(EvidenceResolutionError, match="needs_review"):
        validate_plan(plan)


def test_validate_allows_needs_review_when_explicitly_confirmed():
    plan = sample_plan("docx")
    plan.fields["head_thickness"] = GroundedValue(value=11.8, unit="mm", evidence_ref="insp-2214#p7.b2")
    resolved = validate_plan(plan, allow_review_spans=True)
    assert "insp-2214#p7.b2" in resolved
    assert resolved["insp-2214#p7.b2"].needs_review is True


def test_validate_requires_calculation_string_when_computed_from_set():
    plan = sample_plan("docx")
    plan.fields["average_thickness"] = GroundedValue(
        value=11.45, unit="mm", computed_from=["insp-2214#p7.b1", "insp-2214#p2.b1"], calculation=None
    )
    with pytest.raises(EvidenceResolutionError, match="calculation"):
        validate_plan(plan)


def test_validate_needs_review_string_field_is_allowed_without_confirmation():
    """The doc's rule gates on "the value is numeric" — a string-valued field citing a
    needs_review span is not the case this rule protects against."""
    plan = sample_plan("docx")
    plan.fields["head_note"] = GroundedValue(value="approximately 11.8 mm", evidence_ref="insp-2214#p7.b2")
    resolved = validate_plan(plan)
    assert "insp-2214#p7.b2" in resolved


# ─────────────────────────── render() — fail closed ────────────────────────────────


def test_render_fails_closed_leaves_no_file():
    plan = sample_plan("docx")
    plan.fields["bad_ref"] = GroundedValue(value=1, evidence_ref="bogus#p1.b1")
    task_id = _unique_task_id("fail-closed")
    out_dir = SETTINGS.paths.outputs / task_id

    with pytest.raises(EvidenceResolutionError):
        render(plan, task_id)

    assert not out_dir.exists() or list(out_dir.iterdir()) == []


def test_render_is_atomic():
    task_id = _unique_task_id("atomic")
    out_path = render(sample_plan("docx"), task_id)
    out_dir = out_path.parent
    leftovers = [p for p in out_dir.iterdir() if p.suffix == ".tmp" or ".tmp" in p.name]
    assert leftovers == []
    assert out_path.is_file()


# ─────────────────────────── DOCX content ───────────────────────────────────────────


def test_docx_contains_provenance_appendix():
    task_id = _unique_task_id("docx-prov")
    out_path = render(sample_plan("docx"), task_id)
    doc = Document(str(out_path))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "PROVENANCE" in full_text
    assert "insp-2214" in full_text
    assert "p.7" in full_text or "p.2" in full_text


def test_docx_contains_every_finding():
    plan = sample_plan("docx")
    task_id = _unique_task_id("docx-findings")
    out_path = render(plan, task_id)
    doc = Document(str(out_path))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    for finding in plan.findings:
        assert finding.title in full_text


def test_calculation_disagreement_renders_banner():
    plan = sample_plan("docx")
    plan.fields["average_thickness"] = GroundedValue(
        value=11.45, unit="mm",
        computed_from=["insp-2214#p7.b1", "insp-2214#p2.b1"],
        calculation="(12.4 + 10.5) / 2 = 12.0\nindependent re-derivation: DISAGREES",
    )
    task_id = _unique_task_id("docx-disagree")
    out_path = render(plan, task_id)
    doc = Document(str(out_path))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "DISAGREES" in full_text
    assert "HUMAN REVIEW REQUIRED" in full_text


# ─────────────────────────── PPTX content ───────────────────────────────────────────


def test_pptx_slide_count_matches_findings_plus_four():
    plan = sample_plan("pptx")
    task_id = _unique_task_id("pptx-count")
    out_path = render(plan, task_id)
    prs = Presentation(str(out_path))
    assert len(prs.slides) == len(plan.findings) + 4


# ─────────────────────────── XLSX content ───────────────────────────────────────────


def test_xlsx_has_three_sheets_and_amber_rows():
    plan = sample_plan("xlsx")
    plan.fields["head_thickness"] = GroundedValue(value=11.8, unit="mm", evidence_ref="insp-2214#p7.b2")
    task_id = _unique_task_id("xlsx-amber")
    out_path = render(plan, task_id, allow_review_spans=True)

    wb = load_workbook(str(out_path))
    assert wb.sheetnames == ["Summary", "Values", "Calculations"]

    values = wb["Values"]
    amber_rows = [
        row for row in values.iter_rows(min_row=2)
        if row[0].fill.start_color.rgb in ("00FFD966", "FFFFD966")
    ]
    assert amber_rows, "expected at least one amber-filled row for the needs_review field"


# ─────────────────────────── file_sha256 ────────────────────────────────────────────


def test_file_sha256_stable():
    task_id = _unique_task_id("sha256")
    out_path = render(sample_plan("xlsx"), task_id)
    first = file_sha256(out_path)
    second = file_sha256(out_path)
    assert first == second
    assert len(first) == 64
