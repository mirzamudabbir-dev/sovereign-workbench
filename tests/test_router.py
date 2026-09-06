"""L2 — tests for the two-stage automatic model router.

Router unit tests must never depend on which profile (vLLM/demo-box vs Ollama/local) is
currently enabled in the repo's manifests/ directory — R4 means the active profile is data,
and it changes. Every non-integration test below builds its own isolated, synthetic manifest
set in tmp_path and points a private ModelRegistry at it via monkeypatch. Only the
@pytest.mark.integration demo-route test reads the real, currently-active REGISTRY, and it
derives its expected model ids from that registry's task_affinities rather than hardcoding
either profile's model names.
"""
from __future__ import annotations

import asyncio

import pytest
import yaml

import core.router as router
from core.router import RouteRequest, capability_filter, route
from core.schemas import Modality, TaskAffinity, TaskType, WorkbenchError
from core.serving import REGISTRY, ModelRegistry

# ─────────────────────────── Fixture manifest builder ──────────────────────────

_GENERAL_VISION = {
    "id": "fx-general-vision",
    "served_model_name": "fixture/general-vision",
    "base_url": "http://127.0.0.1:9001/v1",
    "licence_class": "permissive",
    "modalities": ["text", "image"],
    "max_context": 32768,
    "vram_gb": 6.0,
    "quantization": "awq",
    "supports_grammar": True,
    "task_affinities": ["drafting", "summarisation", "general_reasoning", "vision_extraction"],
    "description": "General-purpose reasoning, drafting and vision model. Fixture only.",
    "enabled": True,
}

_CODER = {
    "id": "fx-coder",
    "served_model_name": "fixture/coder",
    "base_url": "http://127.0.0.1:9002/v1",
    "licence_class": "permissive",
    "modalities": ["text"],
    "max_context": 16384,
    "vram_gb": 4.0,
    "quantization": "awq",
    "supports_grammar": True,
    "task_affinities": ["coding"],
    "description": "Specialised code model. Fixture only.",
    "enabled": True,
}

_OCR = {
    "id": "fx-ocr",
    "served_model_name": "fixture/ocr",
    "base_url": "http://127.0.0.1:9003/v1",
    "licence_class": "permissive",
    "modalities": ["text", "image"],
    "max_context": 8192,
    "vram_gb": 2.0,
    "quantization": "none",
    "supports_grammar": False,
    "task_affinities": ["ocr_extraction"],
    "description": "OCR/layout extraction model. Fixture only, internal use only.",
    "enabled": True,
}

_ROUTER = {
    "id": "fx-router",
    "served_model_name": "fixture/router",
    "base_url": "http://127.0.0.1:9004/v1",
    "licence_class": "permissive",
    "modalities": ["text"],
    "max_context": 8192,
    "vram_gb": 3.0,
    "quantization": "none",
    "supports_grammar": True,
    "task_affinities": ["routing"],
    "description": "Routing-only model. Fixture only, internal use only.",
    "enabled": True,
}

_BASELINE_MANIFESTS = [_GENERAL_VISION, _CODER, _OCR, _ROUTER]


def _write_manifests(tmp_path, manifests) -> None:
    for manifest in manifests:
        (tmp_path / f"{manifest['id']}.yaml").write_text(yaml.safe_dump(manifest))


def _build_registry(tmp_path, manifests=_BASELINE_MANIFESTS) -> ModelRegistry:
    """Write `manifests` as YAML files into tmp_path and return a ModelRegistry scoped to
    just that directory — fully isolated from the repo's real manifests/ contents."""
    _write_manifests(tmp_path, manifests)
    return ModelRegistry(tmp_path)


@pytest.fixture
def fixture_registry(tmp_path, monkeypatch):
    """Point core.router's REGISTRY at an isolated, synthetic manifest set for the duration
    of one test, regardless of which profile is enabled on disk in the real manifests/."""
    registry = _build_registry(tmp_path)
    monkeypatch.setattr(router, "REGISTRY", registry)
    return registry


def _unique_model_with_affinities(*required: TaskAffinity) -> str:
    """Find the single enabled manifest in the currently-active (real) REGISTRY whose
    task_affinities is a superset of `required`. Used only by the integration demo-route
    test, so it stays correct across both the vLLM and Ollama profiles without hardcoding
    either one's model ids — it fails loudly, not silently, if the active profile's shape
    changes (e.g. two models now share an affinity)."""
    matches = [m for m in REGISTRY.all() if set(required) <= set(m.task_affinities)]
    assert len(matches) == 1, (
        f"expected exactly one enabled model with affinities {required}, "
        f"found {[m.id for m in matches]} — update this test if the active profile's shape changed"
    )
    return matches[0].id


# ─────────────────────────── Stage 1 — capability filter ──────────────────────


def test_filter_removes_text_only_model_for_image_request(fixture_registry):
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="What equipment is shown in this drawing?",
        required_modalities=[Modality.TEXT, Modality.IMAGE],
    )
    survivors, rejected = capability_filter(req)

    assert "fx-coder" in rejected
    assert "fx-coder" not in {m.id for m in survivors}
    assert "image" in rejected["fx-coder"]


def test_filter_removes_short_context_model(fixture_registry):
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="Summarise this very long document",
        estimated_tokens=20_000,
    )
    survivors, rejected = capability_filter(req)
    survivor_ids = {m.id for m in survivors}

    # fx-coder (16384) and fx-ocr (8192) are both too small; only fx-general-vision
    # (32768) fits.
    assert survivor_ids == {"fx-general-vision"}
    assert "fx-coder" in rejected
    assert "16384" in rejected["fx-coder"]
    assert "fx-ocr" in rejected


def test_filter_removes_non_grammar_model_when_structured_required(fixture_registry):
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="Extract findings as structured JSON",
        required_modalities=[Modality.TEXT, Modality.IMAGE],
        needs_structured_output=True,
    )
    survivors, rejected = capability_filter(req)

    assert "fx-ocr" in rejected
    assert "fx-ocr" not in {m.id for m in survivors}
    assert "constrained decoding" in rejected["fx-ocr"]


def test_filter_excludes_router_and_ocr_from_general_routing(fixture_registry):
    """P1-4: internal-only manifests (routing-only, ocr-only) are excluded from every
    general-purpose route unconditionally — the affinity filter no longer depends on the
    request's excluded_affinity field, it looks at whether *every* affinity a manifest
    declares is internal-only."""
    req = RouteRequest(step_id="t.s1", task_type=TaskType.CODING, instruction="write some code")
    survivors, rejected = capability_filter(req)
    survivor_ids = {m.id for m in survivors}

    assert "fx-router" in rejected
    assert "fx-router" not in survivor_ids
    assert "fx-ocr" in rejected
    assert "fx-ocr" not in survivor_ids


def test_rejection_reasons_are_human_readable(fixture_registry):
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


def test_zero_survivors_raises_with_table(fixture_registry):
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="impossible request",
        estimated_tokens=10_000_000,
    )
    with pytest.raises(WorkbenchError) as excinfo:
        # zero survivors: every fixture manifest's max_context is below 10,000,000
        asyncio.run(route(req))

    message = str(excinfo.value)
    for manifest in _BASELINE_MANIFESTS:
        assert manifest["id"] in message


@pytest.mark.asyncio
async def test_single_survivor_skips_llm_call(fixture_registry, monkeypatch):
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
    assert decision.chosen_model == "fx-general-vision"
    assert decision.reason == "only capable model"
    assert decision.candidates_considered == ["fx-general-vision"]


def test_ocr_model_excluded_from_general_vision_routing(fixture_registry):
    """P1-4 regression: an image request must not offer the OCR extractor as a candidate
    for general vision reasoning — Arch-Router should never even see it as an option."""
    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="What equipment is in this drawing?",
        required_modalities=[Modality.TEXT, Modality.IMAGE],
    )
    survivors, rejected = capability_filter(req)
    survivor_ids = {m.id for m in survivors}

    assert survivor_ids == {"fx-general-vision"}
    assert "fx-ocr" in rejected
    assert "fx-ocr" not in survivor_ids


@pytest.mark.asyncio
async def test_router_failure_falls_back_to_first_candidate(fixture_registry, monkeypatch):
    """P1-5 regression: an exception from complete_structured() (e.g. a router timeout)
    must not kill the task — it should fall back to the first surviving candidate."""

    async def boom(*_args, **_kwargs):
        raise WorkbenchError("router timed out")

    monkeypatch.setattr(router, "complete_structured", boom)

    req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="Summarise this inspection report",
    )
    decision = await route(req)

    assert decision.chosen_model in decision.candidates_considered
    assert decision.chosen_model == decision.candidates_considered[0]
    assert "router unavailable" in decision.reason


def test_new_manifest_is_routable_without_code_change(tmp_path, monkeypatch):
    """This test IS R4: adding a manifest requires zero Python edits."""
    _write_manifests(tmp_path, _BASELINE_MANIFESTS)

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
    """Expected model ids are derived from the currently-active REGISTRY's task_affinities,
    not hardcoded — this test must pass unmodified whether the vLLM or Ollama profile is
    the one with `enabled: true` in manifests/."""
    general_model = _unique_model_with_affinities(
        TaskAffinity.GENERAL_REASONING, TaskAffinity.VISION_EXTRACTION
    )
    coding_model = _unique_model_with_affinities(TaskAffinity.CODING)

    text_req = RouteRequest(
        step_id="t.s1",
        task_type=TaskType.DOC_QA,
        instruction="Summarise this inspection report",
    )
    decision = await route(text_req)
    assert decision.chosen_model == general_model

    coding_req = RouteRequest(
        step_id="t.s2",
        task_type=TaskType.CODING,
        instruction="Write a Python function to parse P&ID tag numbers",
    )
    decision = await route(coding_req)
    assert decision.chosen_model == coding_model

    image_req = RouteRequest(
        step_id="t.s3",
        task_type=TaskType.DOC_QA,
        instruction="What equipment is shown in this drawing?",
        required_modalities=[Modality.TEXT, Modality.IMAGE],
    )
    decision = await route(image_req)
    assert decision.chosen_model == general_model

    long_req = RouteRequest(
        step_id="t.s4",
        task_type=TaskType.DOC_QA,
        instruction="Summarise this extremely long report",
        estimated_tokens=20_000,
    )
    decision = await route(long_req)
    assert decision.chosen_model == general_model
