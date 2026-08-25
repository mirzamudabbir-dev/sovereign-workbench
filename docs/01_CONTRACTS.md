# 01_CONTRACTS — Shared Types (read by EVERY session)

> This is the narrow waist of the system. Every layer talks to every other layer through these
> types and nothing else. **This file is small on purpose — read it fully, every session.**
>
> Owner: the CONTRACTS session (Session 0). After Session 0, these types are **frozen**.
> If a later layer needs a field that does not exist: add it as `Optional` with a default,
> note it in `PROGRESS.md`, and never change or remove an existing field.

## Ports & endpoints (memorise; do not invent others)

| Service | Port | Notes |
|---|---|---|
| vLLM — Qwen2.5-VL-7B-AWQ (general + vision) | 8001 | OpenAI-compatible |
| vLLM — Qwen2.5-Coder-7B-AWQ (coding) | 8002 | OpenAI-compatible |
| vLLM — Arch-Router-1.5B (routing) | 8003 | OpenAI-compatible |
| vLLM — PaddleOCR-VL (OCR/vision extraction) | 8004 | OpenAI-compatible, image input |
| Qdrant | 6333 | HTTP |
| FastAPI backend | 8000 | |
| Streamlit UI | 8501 | |

All are bound to `127.0.0.1` only. Never `0.0.0.0`.

## `core/schemas.py` — implement exactly this

```python
"""Shared cross-layer contracts. FROZEN after Session 0."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────── Evidence & documents (L3, L6 → all) ──────────────

class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"


class DocKind(str, Enum):
    NATIVE_PDF = "native_pdf"      # born-digital, has a text layer
    SCANNED_PDF = "scanned_pdf"    # raster pages, needs OCR
    IMAGE = "image"                # photo / drawing scan
    OFFICE = "office"              # docx/xlsx/pptx
    PLAINTEXT = "plaintext"


class EvidenceSpan(BaseModel):
    """The atom of provenance. Nothing enters a deliverable without one."""
    span_id: str                       # "insp-2214#p7.b1"  (doc_id#p{page}.b{block})
    doc_id: str
    page: int                          # 1-indexed
    bbox: tuple[float, float, float, float]  # normalised x0,y0,x1,y1 in [0,1]
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    extractor: str                     # "docling" | "paddleocr-vl" | "native"
    needs_review: bool = False         # True when confidence < threshold (handwriting)


class DocumentRef(BaseModel):
    doc_id: str
    filename: str
    path: str                          # absolute path on the host
    kind: DocKind
    page_count: int
    page_images: list[str] = []        # absolute paths to rendered page PNGs
    ingested_at: datetime


# ─────────────────────────── Model registry (L1 → L2) ─────────────────────────

class LicenceClass(str, Enum):
    PERMISSIVE = "permissive"          # Apache-2.0, MIT
    RESTRICTED = "restricted"          # community licences with carve-outs
    REVIEW_REQUIRED = "review_required"


class TaskAffinity(str, Enum):
    DRAFTING = "drafting"
    SUMMARISATION = "summarisation"
    GENERAL_REASONING = "general_reasoning"
    CODING = "coding"
    VISION_EXTRACTION = "vision_extraction"
    ROUTING = "routing"


class ModelManifest(BaseModel):
    """One YAML file in manifests/. Adding a model = adding one of these. (R4)"""
    id: str                            # "qwen25-vl-7b"
    served_model_name: str             # exact string vLLM answers to
    base_url: str                      # "http://127.0.0.1:8001/v1"
    weights_sha256: str | None = None
    licence_class: LicenceClass
    modalities: list[Modality]
    max_context: int
    vram_gb: float
    quantization: str                  # "awq" | "fp8" | "none" | "mxfp4"
    supports_grammar: bool
    task_affinities: list[TaskAffinity]
    description: str                   # one line, fed to Arch-Router as the route policy
    enabled: bool = True


# ─────────────────────────── Tasks & routing (L7 → L4 → L2) ───────────────────

class TaskType(str, Enum):
    DOC_TO_DELIVERABLE = "doc_to_deliverable"   # R13 flagship
    CODING = "coding"                            # R14
    DOC_QA = "doc_qa"                            # R15
    CALCULATION = "calculation"


class TaskSpec(BaseModel):
    task_id: str
    task_type: TaskType
    instruction: str
    doc_ids: list[str] = []
    template_id: str | None = None     # e.g. "approval_note_v1"
    created_at: datetime


class RouteDecision(BaseModel):
    """Rendered verbatim in the UI — this IS the R12 demo artifact."""
    step_id: str
    required_modalities: list[Modality]
    estimated_tokens: int
    needs_structured_output: bool
    candidates_considered: list[str]   # model ids surviving the capability filter
    rejected: dict[str, str]           # model_id -> human-readable rejection reason
    chosen_model: str
    reason: str                        # why Arch-Router picked it
    latency_ms: float


# ─────────────────────────── Agent loop (L4 internal, L8 consumes) ────────────

class StepKind(str, Enum):
    RETRIEVE = "retrieve"
    INGEST = "ingest"
    EXECUTE_CODE = "execute_code"
    LLM_CALL = "llm_call"
    RENDER = "render"


class PlanStep(BaseModel):
    step_id: str
    kind: StepKind
    description: str
    payload: dict[str, Any] = {}
    done: bool = False
    output_summary: str | None = None


class ToolCall(BaseModel):
    call_id: str
    step_id: str
    tool_name: str                     # "fs.read" | "code.exec" | "sheet.write" | "kb.search"
    args_sha256: str                   # hash, not raw args — receipts stay small
    started_at: datetime
    duration_ms: float
    ok: bool
    error: str | None = None


class SandboxResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    artifacts: list[str] = []          # paths inside the task workspace
    timed_out: bool = False


# ─────────────────────────── Deliverables (L4 → L7b) ──────────────────────────

class GroundedValue(BaseModel):
    """A value the model asserts. MUST cite evidence unless computed."""
    value: str | float | int
    unit: str | None = None
    evidence_ref: str | None = None    # span_id; required unless computed_from is set
    computed_from: list[str] = []      # span_ids used in a calculation
    calculation: str | None = None     # the Python expression, shown in the deliverable (R9)


class Finding(BaseModel):
    title: str
    detail: str
    severity: Literal["info", "observation", "concern", "critical"]
    evidence_refs: list[str] = Field(min_length=1)


class RenderPlan(BaseModel):
    """Grammar-constrained LLM output. The LLM produces this; Python produces the file."""
    template_id: str                   # "approval_note_v1" | "board_deck_v1" | "calc_sheet_v1"
    output_format: Literal["docx", "pptx", "xlsx"]
    title: str
    fields: dict[str, GroundedValue] = {}
    findings: list[Finding] = []
    recommendation: str
    prepared_by: str = "Sovereign Workbench (draft — requires human approval)"


# ─────────────────────────── Audit (L8) ───────────────────────────────────────

class EgressEvent(BaseModel):
    timestamp: datetime
    binary: str
    pid: int
    destination_ip: str
    destination_port: int
    action: Literal["observed", "blocked"]
    is_external: bool                  # not loopback and not RFC1918


class TaskReceipt(BaseModel):
    """The R16 proof artifact. Signed, offline-verifiable, independent of the UI."""
    task_id: str
    started_at: datetime
    finished_at: datetime
    model_manifests: dict[str, str]    # model_id -> weights_sha256 (or manifest sha)
    route_decisions: list[RouteDecision]
    tool_trace: list[ToolCall]
    egress_events: list[EgressEvent]
    external_egress_count: int         # MUST be 0 for a clean receipt
    artifact_hashes: dict[str, str]    # filename -> sha256
    payload_sha256: str                # hash of the canonical JSON of all fields above
    signature_ed25519: str             # hex
    public_key_ed25519: str            # hex
```

## `core/config.py` — implement exactly this

```python
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

def load_settings(path: str | Path = "config.yaml") -> Settings: ...
SETTINGS = load_settings()   # module-level singleton; import this everywhere
```

## Conventions every layer follows

- **IDs:** `task_id` = `t-{YYYYMMDD}-{6 hex}`. `doc_id` = slugified filename + 4 hex.
  `span_id` = `{doc_id}#p{page}.b{block_index}`. `step_id` = `{task_id}.s{n}`.
- **Paths:** always absolute, always from `SETTINGS.paths`. Never hardcode `/tmp` or `./data`.
- **Errors:** raise `WorkbenchError` (define in `core/schemas.py`) with a human-readable message.
  Never swallow an exception silently. Never `except: pass`.
- **Logging:** stdlib `logging`, logger name = module name. No print() in `core/`.
- **Async:** `core/serving.py`, `core/router.py`, `core/graph.py` are async.
  `core/ingest.py`, `core/kb.py`, `core/render.py`, `core/sandbox.py`, `core/receipt.py` are sync.
- **No LLM call anywhere except through `core/serving.py`.** If a layer needs an LLM, it calls
  `route_and_complete()`. Direct `openai.AsyncOpenAI(...)` outside `serving.py` is a bug.
