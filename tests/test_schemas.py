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
    """Structural assertions only — config.yaml's runtime values (sandbox.runtime,
    router_model_id, serving_backend, ...) are profile data (vLLM/demo-box vs
    Ollama/local) and change with the active profile. This test must stay green
    regardless of which profile is currently configured."""
    settings = load_settings(REPO_ROOT / "config.yaml")

    assert isinstance(settings, Settings)
    assert Path(settings.paths.data).is_absolute()
    assert Path(settings.paths.manifests).is_absolute()
    assert isinstance(settings.sandbox.runtime, str) and settings.sandbox.runtime
    assert isinstance(settings.agent.max_iterations, int) and settings.agent.max_iterations > 0
    assert isinstance(settings.router_model_id, str) and settings.router_model_id


# ─────────────────────────── P0-1 · CWD independence ───────────────────────────


def test_load_settings_works_from_any_cwd(monkeypatch, tmp_path):
    """Importing core.config (and calling load_settings() with no args) must not depend
    on the process's current working directory — only on the repo root."""
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert Path(settings.paths.data) == REPO_ROOT / "data"
    assert Path(settings.paths.manifests) == REPO_ROOT / "manifests"


# ─────────────────────────── P0-2 · directories get created ───────────────────


def test_load_settings_creates_directories(tmp_path):
    config = {
        "paths": {
            "data": str(tmp_path / "data"),
            "uploads": str(tmp_path / "data" / "uploads"),
            "page_images": str(tmp_path / "data" / "page_images"),
            "workspaces": str(tmp_path / "data" / "workspaces"),
            "outputs": str(tmp_path / "data" / "outputs"),
            "receipts": str(tmp_path / "data" / "receipts"),
            "manifests": str(REPO_ROOT / "manifests"),
            "templates": str(REPO_ROOT / "templates"),
        },
        "sandbox": {},
        "agent": {},
        "embedding_model_path": str(tmp_path / "models" / "bge-m3"),
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    settings = load_settings(config_path)

    assert Path(settings.paths.data).is_dir()
    assert Path(settings.paths.uploads).is_dir()
    assert Path(settings.paths.page_images).is_dir()
    assert Path(settings.paths.workspaces).is_dir()
    assert Path(settings.paths.outputs).is_dir()
    assert Path(settings.paths.receipts).is_dir()


# ─────────────────────────── P2-9 · EvidenceSpan.bbox validation ──────────────


def test_evidence_span_rejects_unnormalised_bbox():
    with pytest.raises(ValidationError):
        EvidenceSpan(
            span_id="insp-2214#p7.b1",
            doc_id="insp-2214",
            page=7,
            bbox=(5.0, -2.0, 900.0, 3.0),
            text="sample text",
            confidence=0.9,
            extractor="native",
        )


def test_evidence_span_rejects_inverted_bbox():
    with pytest.raises(ValidationError):
        EvidenceSpan(
            span_id="insp-2214#p7.b1",
            doc_id="insp-2214",
            page=7,
            bbox=(0.8, 0.2, 0.1, 0.9),
            text="sample text",
            confidence=0.9,
            extractor="native",
        )


# ─────────────────────────── P0-3 · policies/ must stay tracked ───────────────


def test_gitignore_does_not_drop_policies():
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert "policies/*" not in gitignore
    assert "*.pem" in gitignore
