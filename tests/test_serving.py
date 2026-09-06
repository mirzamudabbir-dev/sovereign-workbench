"""L1 — tests for the model registry and unified inference client."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from core.config import SETTINGS
from core.schemas import Modality, WorkbenchError
from core.serving import (
    REGISTRY,
    ModelRegistry,
    _structured_kwargs,
    complete,
    complete_structured,
    estimate_tokens,
    health,
)

MANIFESTS_DIR = SETTINGS.paths.manifests


def _any_enabled_model_id() -> str:
    return REGISTRY.all()[0].id


def _enabled_text_only_model_id() -> str:
    for m in REGISTRY.all():
        if Modality.IMAGE not in m.modalities:
            return m.id
    raise AssertionError("expected at least one enabled text-only model in the active profile")


def _enabled_grammar_model_id() -> str:
    for m in REGISTRY.all():
        if m.supports_grammar:
            return m.id
    raise AssertionError("expected at least one enabled grammar-capable model in the active profile")


def test_registry_loads_four_manifests():
    """Structural check only — the specific ids depend on which profile (vLLM/demo-box vs
    Ollama/local) is enabled in manifests/; R4 means that's data, not something to hardcode.
    Cross-checked against the manifest files' own `enabled` flags on disk."""
    enabled_ids_on_disk = set()
    for yaml_path in MANIFESTS_DIR.glob("*.yaml"):
        raw = yaml.safe_load(yaml_path.read_text())
        if raw.get("enabled", True):
            enabled_ids_on_disk.add(raw["id"])

    ids = {m.id for m in REGISTRY.all()}
    assert ids == enabled_ids_on_disk
    assert len(ids) == 4


def test_registry_reload_picks_up_new_file(tmp_path):
    """This test IS R4: adding a manifest requires zero Python edits."""
    for yaml_file in MANIFESTS_DIR.glob("*.yaml"):
        shutil.copy(yaml_file, tmp_path / yaml_file.name)

    registry = ModelRegistry(tmp_path)
    assert len(registry.all()) == 4

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

    registry.reload()
    assert len(registry.all()) == 5


def test_get_unknown_model_raises():
    with pytest.raises(WorkbenchError):
        REGISTRY.get("does-not-exist")


def test_get_disabled_model_raises(tmp_path):
    """P1-6 regression: REGISTRY.get() must honor the enabled kill switch, same as all()."""
    for yaml_file in MANIFESTS_DIR.glob("*.yaml"):
        shutil.copy(yaml_file, tmp_path / yaml_file.name)

    disabled = yaml.safe_load((tmp_path / "qwen25-coder-1.5b.yaml").read_text())
    disabled["enabled"] = False
    (tmp_path / "qwen25-coder-1.5b.yaml").write_text(yaml.safe_dump(disabled))

    registry = ModelRegistry(tmp_path)

    assert "qwen25-coder-1.5b" not in {m.id for m in registry.all()}
    with pytest.raises(WorkbenchError):
        registry.get("qwen25-coder-1.5b")

    # the kill switch does not hide the manifest from receipts
    assert "qwen25-coder-1.5b" in registry.manifest_hashes()
    # and can be bypassed explicitly when a caller genuinely needs the disabled manifest
    assert registry.get("qwen25-coder-1.5b", include_disabled=True).id == "qwen25-coder-1.5b"


def test_estimate_tokens_counts_images():
    messages = [{"role": "user", "content": "hello world"}]
    no_images = estimate_tokens(messages)
    with_images = estimate_tokens(
        messages, images=[Path("/nonexistent/a.png"), Path("/nonexistent/b.png")]
    )
    assert with_images == no_images + 1600


def test_complete_rejects_images_for_text_only_model():
    messages = [{"role": "user", "content": "describe this"}]
    with pytest.raises(WorkbenchError):
        asyncio.run(
            complete(
                _enabled_text_only_model_id(), messages, images=[Path("/nonexistent/a.png")]
            )
        )


def _make_empty_content_response():
    class _Msg:
        content = None

    class _Choice:
        message = _Msg()

    class _Response:
        choices = [_Choice()]

    return _Response()


def test_complete_raises_on_empty_content(monkeypatch):
    """P2-8 regression: complete() is typed `-> str` but message.content can be None."""
    import core.serving as serving

    async def fake_call_with_retry(_func, **_kwargs):
        return _make_empty_content_response()

    monkeypatch.setattr(serving, "_call_with_retry", fake_call_with_retry)

    messages = [{"role": "user", "content": "hello"}]
    with pytest.raises(WorkbenchError):
        asyncio.run(complete(_any_enabled_model_id(), messages))


def test_complete_structured_raises_on_empty_content(monkeypatch):
    """P2-8 regression: same None-content guard before model_validate_json is called."""
    import core.serving as serving

    class TinySchema(BaseModel):
        answer: str

    async def fake_call_with_retry(_func, **_kwargs):
        return _make_empty_content_response()

    monkeypatch.setattr(serving, "_call_with_retry", fake_call_with_retry)

    messages = [{"role": "user", "content": "hello"}]
    with pytest.raises(WorkbenchError):
        asyncio.run(complete_structured(_enabled_grammar_model_id(), messages, TinySchema))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_all_green():
    results = await health()
    assert results, "expected at least one manifest"
    assert all(results.values()), f"not all models healthy: {results}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_structured_returns_valid_model():
    class TinySchema(BaseModel):
        answer: str
        confidence: float

    messages = [{"role": "user", "content": "Reply with answer='yes' and confidence=0.9 as JSON."}]
    result = await complete_structured(_enabled_grammar_model_id(), messages, TinySchema)
    assert isinstance(result, TinySchema)


def test_structured_kwargs_guided_json(monkeypatch):
    monkeypatch.setattr(SETTINGS, "structured_output_mode", "guided_json")
    schema = {"type": "object", "properties": {}}
    assert _structured_kwargs(schema) == {"extra_body": {"guided_json": schema}}


def test_structured_kwargs_response_format(monkeypatch):
    monkeypatch.setattr(SETTINGS, "structured_output_mode", "response_format")
    schema = {"type": "object", "properties": {}}
    assert _structured_kwargs(schema) == {
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "out", "schema": schema, "strict": True},
        }
    }


def test_structured_kwargs_ollama_format(monkeypatch):
    monkeypatch.setattr(SETTINGS, "structured_output_mode", "ollama_format")
    schema = {"type": "object", "properties": {}}
    assert _structured_kwargs(schema) == {"extra_body": {"format": schema}}
