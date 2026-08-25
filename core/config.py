from pathlib import Path
import yaml
from pydantic import BaseModel


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


class Settings(BaseModel):
    paths: Paths
    sandbox: SandboxCfg
    agent: AgentCfg
    qdrant_url: str = "http://127.0.0.1:6333"
    embedding_model_path: str
    router_model_id: str = "arch-router-1.5b"
    ocr_model_id: str = "paddleocr-vl"


def load_settings(path: str | Path = "config.yaml") -> Settings:
    config_path = Path(path).resolve()
    with config_path.open("r") as f:
        raw = yaml.safe_load(f)

    base_dir = config_path.parent
    raw["paths"] = {
        key: str((base_dir / value).resolve())
        for key, value in raw["paths"].items()
    }
    raw["embedding_model_path"] = str((base_dir / raw["embedding_model_path"]).resolve())

    return Settings(**raw)


SETTINGS = load_settings()   # module-level singleton; import this everywhere
