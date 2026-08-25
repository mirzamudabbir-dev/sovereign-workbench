"""L2 — tests for the two-stage automatic model router."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

import core.router as router
from core.config import SETTINGS
from core.router import RouteRequest, capability_filter, route
from core.schemas import Modality, TaskAffinity, TaskType, WorkbenchError
from core.serving import ModelRegistry

MANIFESTS_DIR = SETTINGS.paths.manifests


# ─────────────────────────── Stage 1 — capability filter ──────────────────────


def test_filter_removes_text_only_model_for_image_request():
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="What equipment is shown in this drawing?",
        required_modalities=[Modality.TEXT, Modality.IMAGE],
    )
    survivors, rejected = capability_filter(req)

    assert "qwen25-coder-7b" in rejected
    assert "qwen25-coder-7b" not in {m.id for m in survivors}
    assert "image" in rejected["qwen25-coder-7b"]


def test_filter_removes_short_context_model():
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="Summarise this very long document",
        estimated_tokens=20_000,
    )
    survivors, rejected = capability_filter(req)
    survivor_ids = {m.id for m in survivors}

    # coder (16384) and paddleocr (8192) are both too small; only qwen25-vl-7b (32768) fits.
    assert survivor_ids == {"qwen25-vl-7b"}
    assert "qwen25-coder-7b" in rejected
    assert "16384" in rejected["qwen25-coder-7b"]
    assert "paddleocr-vl" in rejected


def test_filter_removes_non_grammar_model_when_structured_required():
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="Extract findings as structured JSON",
        required_modalities=[Modality.TEXT, Modality.IMAGE],
        needs_structured_output=True,
    )
    survivors, rejected = capability_filter(req)

    assert "paddleocr-vl" in rejected
    assert "paddleocr-vl" not in {m.id for m in survivors}
    assert "constrained decoding" in rejected["paddleocr-vl"]


def test_filter_excludes_router_and_ocr_from_general_routing():
    default_req = RouteRequest(
        step_id="t.s1", task_type=TaskType.CODING, instruction="write some code"
    )
    survivors, rejected = capability_filter(default_req)
    assert "arch-router-1.5b" in rejected
    assert "arch-router-1.5b" not in {m.id for m in survivors}

    ocr_excluded_req = RouteRequest(
        step_id="t.s2",
        task_type=TaskType.CODING,
        instruction="write some code",
        excluded_affinity=TaskAffinity.VISION_EXTRACTION,
    )
    survivors, rejected = capability_filter(ocr_excluded_req)
    assert "paddleocr-vl" in rejected
    assert "paddleocr-vl" not in {m.id for m in survivors}


def test_rejection_reasons_are_human_readable():
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="anything",
        required_modalities=[Modality.TEXT, Modality.IMAGE],
        needs_structured_output=True,
    )
    _survivors, rejected = capability_filter(req)

    assert rejected, "expected at least one rejection to exercise this test"
    for model_id, reason in rejected.items():
        assert "_" not in reason, f"reason for {model_id!r} looks like a code, not English: {reason!r}"
        assert " " in reason, f"reason for {model_id!r} is not a readable sentence: {reason!r}"
        assert not reason.isupper()


def test_zero_survivors_raises_with_table():
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="impossible request",
        estimated_tokens=10_000_000,
    )
    with pytest.raises(WorkbenchError) as excinfo:
        # zero survivors: every real manifest's max_context is below 10,000,000
        import asyncio

        asyncio.run(route(req))

    message = str(excinfo.value)
    for model_id in ("qwen25-vl-7b", "qwen25-coder-7b", "paddleocr-vl", "arch-router-1.5b"):
        assert model_id in message


@pytest.mark.asyncio
async def test_single_survivor_skips_llm_call(monkeypatch):
    called = False

    async def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("Arch-Router must not be called when there is a single survivor")

    monkeypatch.setattr(router, "_arch_router_select", fail_if_called)

    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="Summarise this very long document",
        estimated_tokens=20_000,
    )
    decision = await route(req)

    assert called is False
    assert decision.chosen_model == "qwen25-vl-7b"
    assert decision.reason == "only capable model"
    assert decision.candidates_considered == ["qwen25-vl-7b"]


def test_new_manifest_is_routable_without_code_change(tmp_path, monkeypatch):
    """This test IS R4: adding a manifest requires zero Python edits."""
    for yaml_file in MANIFESTS_DIR.glob("*.yaml"):
        shutil.copy(yaml_file, tmp_path / yaml_file.name)

    fifth_manifest = {
        "id": "test-fifth-model",
        "served_model_name": "test/fifth-model",
        "base_url": "http://127.0.0.1:8099/v1",
        "licence_class": "permissive",
        "modalities": ["text"],
        "max_context": 4096,
        "vram_gb": 1.0,
        "quantization": "none",
        "supports_grammar": True,
        "task_affinities": ["general_reasoning"],
        "description": "A fifth manifest added purely to prove R4: zero Python edits needed.",
        "enabled": True,
    }
    (tmp_path / "fifth-model.yaml").write_text(yaml.safe_dump(fifth_manifest))

    test_registry = ModelRegistry(tmp_path)
    monkeypatch.setattr(router, "REGISTRY", test_registry)

    req = RouteRequest(
        step_id="t.s1", task_type=TaskType.DOC_QA, instruction="anything at all"
    )
    survivors, _rejected = capability_filter(req)

    assert "test-fifth-model" in {m.id for m in survivors}


# ─────────────────────────── R12 demo script (needs live Arch-Router) ─────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_four_demo_routes():
    text_req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="Summarise this inspection report",
    )
    decision = await route(text_req)
    assert decision.chosen_model == "qwen25-vl-7b"

    coding_req = RouteRequest(
        step_id="t.s2",
        task_type=TaskType.CODING,
        instruction="Write a Python function to parse P&ID tag numbers",
    )
    decision = await route(coding_req)
    assert decision.chosen_model == "qwen25-coder-7b"

    image_req = RouteRequest(
        step_id="t.s3",
        task_type=TaskType.DOC_QA,
        instruction="What equipment is shown in this drawing?",
        required_modalities=[Modality.TEXT, Modality.IMAGE],
    )
    decision = await route(image_req)
    assert decision.chosen_model == "qwen25-vl-7b"

    long_req = RouteRequest(
        step_id="t.s4",
        task_type=TaskType.DOC_QA,
        instruction="Summarise this extremely long report",
        estimated_tokens=20_000,
    )
    decision = await route(long_req)
    assert decision.chosen_model == "qwen25-vl-7b"
