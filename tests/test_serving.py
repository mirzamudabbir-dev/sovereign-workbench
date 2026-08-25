"""L1 — tests for the model registry and unified inference client."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from core.config import SETTINGS
from core.schemas import WorkbenchError
from core.serving import (
    REGISTRY,
    ModelRegistry,
    complete,
    complete_structured,
    estimate_tokens,
    health,
)

MANIFESTS_DIR = SETTINGS.paths.manifests


def test_registry_loads_four_manifests():
    ids = {m.id for m in REGISTRY.all()}
    assert ids == {"qwen25-vl-7b", "qwen25-coder-7b", "arch-router-1.5b", "paddleocr-vl"}
    assert len(REGISTRY.all()) == 4


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
            complete("qwen25-coder-7b", messages, images=[Path("/nonexistent/a.png")])
        )


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
    result = await complete_structured("qwen25-vl-7b", messages, TinySchema)
    assert isinstance(result, TinySchema)
