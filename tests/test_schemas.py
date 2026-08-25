"""Tests for core/schemas.py and core/config.py (Session 0 — CONTRACTS)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from core.config import Settings, load_settings
from core.schemas import EvidenceSpan, Finding, ModelManifest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_evidence_span_rejects_confidence_above_one():
    with pytest.raises(ValidationError):
        EvidenceSpan(
            span_id="insp-2214#p7.b1",
            doc_id="insp-2214",
            page=7,
            bbox=(0.0, 0.0, 1.0, 1.0),
            text="sample text",
            confidence=1.5,
            extractor="native",
        )


def test_finding_rejects_empty_evidence_refs():
    with pytest.raises(ValidationError):
        Finding(
            title="Corrosion on flange",
            detail="Visible pitting corrosion observed on flange face.",
            severity="concern",
            evidence_refs=[],
        )


def test_model_manifest_round_trips_through_yaml():
    manifest = ModelManifest(
        id="qwen25-vl-7b",
        served_model_name="qwen2.5-vl-7b-awq",
        base_url="http://127.0.0.1:8001/v1",
        licence_class="permissive",
        modalities=["text", "image"],
        max_context=32768,
        vram_gb=16.0,
        quantization="awq",
        supports_grammar=True,
        task_affinities=["general_reasoning", "vision_extraction"],
        description="General-purpose vision-language model.",
    )

    dumped = yaml.safe_dump(manifest.model_dump(mode="json"))
    loaded = yaml.safe_load(dumped)
    round_tripped = ModelManifest(**loaded)

    assert round_tripped == manifest


def test_load_settings_parses_config_yaml():
    settings = load_settings(REPO_ROOT / "config.yaml")

    assert isinstance(settings, Settings)
    assert Path(settings.paths.data).is_absolute()
    assert Path(settings.paths.manifests).is_absolute()
    assert settings.sandbox.runtime == "runsc"
    assert settings.agent.max_iterations == 3
    assert settings.router_model_id == "arch-router-1.5b"
