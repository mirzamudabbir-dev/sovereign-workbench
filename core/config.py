from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from core.schemas import WorkbenchError

_REPO_ROOT = Path(__file__).resolve().parent.parent


class Paths(BaseModel):
    data: Path; uploads: Path; page_images: Path
    workspaces: Path; outputs: Path; receipts: Path; manifests: Path; templates: Path


class SandboxCfg(BaseModel):
    image: str = "sovereign-sandbox:latest"
    runtime: str = "runsc"             # gVisor. Fallback "runc" ONLY if runsc unavailable.
    timeout_s: int = 60
    mem_limit: str = "2g"
    pids_limit: int = 64


class AgentCfg(BaseModel):
    max_iterations: int = 3
    ocr_review_threshold: float = 0.75


class AuditCfg(BaseModel):
    egress_source: Literal["pktap", "tetragon"] = "tetragon"


class Settings(BaseModel):
    paths: Paths
    sandbox: SandboxCfg
    agent: AgentCfg
    qdrant_url: str = "http://127.0.0.1:6333"
    embedding_model_path: str
    router_model_id: str = "arch-router-1.5b"
    ocr_model_id: str = "paddleocr-vl"
    serving_backend: Literal["vllm", "ollama"] = "vllm"
    structured_output_mode: Literal["guided_json", "response_format", "ollama_format"] = "guided_json"
    audit: AuditCfg = AuditCfg()


def load_settings(path: str | Path | None = None) -> Settings:
    config_path = Path(path) if path is not None else _REPO_ROOT / "config.yaml"
    config_path = config_path if config_path.is_absolute() else (_REPO_ROOT / config_path)
    config_path = config_path.resolve()
    if not config_path.exists():
        raise WorkbenchError(f"config not found: {config_path}")

    with config_path.open("r") as f:
        raw = yaml.safe_load(f)

    base_dir = _REPO_ROOT          # anchor paths to the repo, never to CWD
    raw["paths"] = {
        key: str((base_dir / value).resolve())
        for key, value in raw["paths"].items()
    }
    raw["embedding_model_path"] = str((base_dir / raw["embedding_model_path"]).resolve())

    settings = Settings(**raw)

    for p in settings.paths.model_dump().values():
        Path(p).mkdir(parents=True, exist_ok=True)

    return settings


SETTINGS = load_settings()   # module-level singleton; import this everywhere
