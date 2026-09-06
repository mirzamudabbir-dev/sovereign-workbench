# PATCH 02 — Local Model Profile (Gemma 4 + Ollama on Apple Silicon)

## MISSION LOCK

**Build:** a second *profile* — a swappable set of manifests plus a serving-backend switch — so
the identical codebase runs on an 8 GB M1 MacBook Air for development and on a Linux box for
the demo. Nothing above L1 changes.

**You are NOT building:** a new architecture, a second codebase, an abstraction layer, or any
layer logic. If you are editing `core/graph.py`, `core/kb.py`, `core/render.py` or
`core/ingest.py`, you are in the wrong session.

**Files You Own:**
```
core/config.py            (add two optional settings — additive only)
core/serving.py           (structured-output backend switch)
manifests/                (replace the four vLLM manifests with the local profile)
config.yaml
scripts/probe_structured.py   (new)
tests/test_serving.py     (add backend tests)
```

---

## Why this is cheap

This migration is the manifest design proving its own R4 claim. Changing inference engine,
hardware architecture *and* model family should touch four YAML files and one function.

If you find yourself editing `core/router.py`, stop — the filter reads manifests, and manifests
are data. That is the whole point, and it is a line worth saying to the judges.

---

## The model stack

Fits in ~7 GB alongside macOS on a base 8 GB M1. All four resident — **no swapping, no
Sleep Mode** (still out of scope).

| id | Ollama tag | Role | RAM |
|---|---|---|---|
| `gemma4-e2b` | `gemma4:e2b` | general reasoning, drafting, **and vision** | ~1.5 GB |
| `qwen25-coder-1.5b` | `qwen2.5-coder:1.5b` | coding | ~1.0 GB |
| `embeddinggemma-300m` | `embeddinggemma` | L6 retrieval (not routed) | ~0.3 GB |
| `gemma4-e2b-ocr` | `gemma4:e2b` | OCR/layout extraction (same weights, OCR role) | shared |

Three notes that matter:

**Gemma 4 E2B is natively multimodal**, so it replaces PaddleOCR-VL. It is Apache-2.0, so
`licence_class: permissive` is correct. **Expect worse OCR than a dedicated extractor** — a
2.3B general VLM doing bounding-box extraction is the biggest quality regression in this
migration. Budget prompt iterations at L3, and keep `paddleocr-vl.yaml` on disk with
`enabled: false` so the demo box can switch back by flipping one boolean.

**There is no current small Gemma coder**, so the coding slot is Qwen. That is fine — routing
across two *different* model families is a more convincing R12 demo than routing within one.

**`gemma4-e2b-ocr` points at the same Ollama tag as `gemma4-e2b`.** Two manifests, one set of
weights. This keeps `ocr_model_id` meaningful and keeps the OCR role excluded from general
routing via `ocr_extraction` (see PATCH 01 · P1-4). Set `weights_sha256` identically on both.

**`vram_gb` now means resident RAM.** Do **not** rename the field — the contract is frozen.
Note the reinterpretation in a comment.

---

## Manifests

`manifests/gemma4-e2b.yaml`
```yaml
id: gemma4-e2b
served_model_name: gemma4:e2b
base_url: http://127.0.0.1:11434/v1
licence_class: permissive          # Apache-2.0
modalities: [text, image]
max_context: 32768
vram_gb: 1.5                       # resident RAM on this profile, not VRAM
quantization: q4_0
supports_grammar: true
task_affinities: [drafting, summarisation, general_reasoning, vision_extraction]
description: >
  General-purpose reasoning and drafting model that also reads images. Use for writing
  approval notes, summarising inspection reports, answering questions about documents, and
  any request that includes a photograph, scan, or engineering drawing.
enabled: true
```

`manifests/qwen25-coder-1.5b.yaml`
```yaml
id: qwen25-coder-1.5b
served_model_name: qwen2.5-coder:1.5b
base_url: http://127.0.0.1:11434/v1
licence_class: permissive
modalities: [text]
max_context: 16384
vram_gb: 1.0
quantization: q4_0
supports_grammar: true
task_affinities: [coding]
description: >
  Specialised code model. Use for writing, fixing, refactoring or explaining source code,
  writing scripts, generating engineering calculations as executable Python, and producing
  test cases.
enabled: true
```

`manifests/gemma4-e2b-ocr.yaml` — same `served_model_name` and `base_url`, but
`task_affinities: [ocr_extraction]`, `supports_grammar: true`, and a description scoped to
raw text-and-bbox extraction. PATCH 01's `_is_internal_only()` keeps it out of general routing.

`manifests/embeddinggemma-300m.yaml` — `task_affinities: [embedding]`,
`modalities: [text]`, `supports_grammar: false`. Also internal-only, also never routed.

Then: `manifests/paddleocr-vl.yaml`, `qwen25-vl-7b.yaml`, `qwen25-coder-7b.yaml`,
`arch-router-1.5b.yaml` → set `enabled: false`. **Do not delete them.** They are the demo-box
profile, and `test_registry_reload_picks_up_new_file` still needs company.

**Routing with no Arch-Router.** Arch-Router-1.5B does not fit this budget. Set
`router_model_id: gemma4-e2b` — the router prompt is built from manifests and constrained by
`_ArchChoice`, so any grammar-capable model can serve it. No code change in `core/router.py`.

---

## Serving backend switch

`core/serving.py`'s `extra_body={"guided_json": ...}` is vLLM-specific. Ollama does not accept it.

**I am not certain which structured-output form your Ollama build accepts** — this has moved
more than once. Do not guess. Implement all three and probe.

```python
# core/config.py — ADDITIVE, both with defaults so existing configs keep working
class Settings(BaseModel):
    ...
    serving_backend: Literal["vllm", "ollama"] = "vllm"
    structured_output_mode: Literal["guided_json", "response_format", "ollama_format"] = "guided_json"
```

```python
# core/serving.py
def _structured_kwargs(schema: dict) -> dict:
    mode = SETTINGS.structured_output_mode
    if mode == "guided_json":
        return {"extra_body": {"guided_json": schema}}
    if mode == "response_format":
        return {"response_format": {"type": "json_schema",
                "json_schema": {"name": "out", "schema": schema, "strict": True}}}
    return {"extra_body": {"format": schema}}          # ollama_format
```
`complete_structured()`'s signature, retry logic and error handling are otherwise unchanged.

`scripts/probe_structured.py` — tries all three modes against the live endpoint with a
two-field schema, prints a PASS/FAIL table and the recommended `config.yaml` value. Run it once
per machine; record the answer in `PROGRESS.md`.

---

## config.yaml for this profile

```yaml
serving_backend:       ollama
structured_output_mode: guided_json     # ← set from scripts/probe_structured.py
embedding_model_path:  ./models/embeddinggemma-300m
router_model_id:       gemma4-e2b
ocr_model_id:          gemma4-e2b-ocr

sandbox:
  runtime: runc          # gVisor is Linux-only; network_mode="none" still holds

audit:
  egress_source: pktap   # macOS dev; "tetragon" on the Linux demo box
```

`audit.egress_source` is additive and is consumed later by L8's `read_egress()`. Add the
`AuditCfg` model now so Session 9 doesn't have to touch `core/config.py`.

---

## L6 dimension change (record, don't implement)

EmbeddingGemma is **768-dimensional**, BGE-M3 is 1024. Session 6 must size the Qdrant dense
vector accordingly. Write this into `PROGRESS.md` under Environment facts — do not edit
`core/kb.py`, it does not exist yet.

---

## Needle 2 — evaluate, do not adopt blind

Needle 2 is a 45M tool-calling model shipping as a ~14 MB binary in ~28 MB of session RAM,
installed with `pip install cactus-needle`. It could take tool-call emission off a small
general model at L5.

**It is not a manifest model.** It has no OpenAI-compatible endpoint, so it does not belong in
`manifests/` and must not be given a `base_url`. If adopted, it lives in `core/tools.py` as a
direct library call.

Three constraints to respect:
- **Single-shot only.** Cactus is explicit that it is a routing layer, not a planner. It cannot
  replace L4.
- **The Cactus SDK has an automatic cloud fallback.** For this project that is an air-gap
  violation. If any Cactus component is used, that path must be provably disabled — and you
  should say so in the pitch, because catching it is exactly the kind of silent egress the
  sovereignty receipt exists to detect.
- **Measure before adopting.** Write `scripts/probe_needle.py`: feed it two real tool schemas
  from `TOOL_REGISTRY`, compare valid-call rate against grammar-constrained `gemma4-e2b` on
  twenty prompts. Adopt only if it wins. Record the numbers in `PROGRESS.md`.

Do not add `cactus-needle` to `requirements.txt` in this session.

---

## Definition of Done

```bash
ollama pull gemma4:e2b && ollama pull qwen2.5-coder:1.5b && ollama pull embeddinggemma
python scripts/probe_structured.py
pytest -q
python -c "
import asyncio; from core.serving import health, REGISTRY
print([m.id for m in REGISTRY.all()])
print(asyncio.run(health()))
"
python -c "
import asyncio; from core.router import route, RouteRequest
from core.schemas import TaskType, Modality
for tt, txt, mods in [
  (TaskType.CODING, 'Write a Python function to parse P&ID tag numbers', [Modality.TEXT]),
  (TaskType.DOC_QA, 'Summarise this inspection report', [Modality.TEXT]),
  (TaskType.DOC_QA, 'What equipment is in this drawing?', [Modality.TEXT, Modality.IMAGE]),
]:
    d = asyncio.run(route(RouteRequest(step_id='s', task_type=tt, instruction=txt,
                                       required_modalities=mods)))
    print(d.chosen_model, '|', d.reason)
"
```
Expected: `qwen25-coder-1.5b`, then `gemma4-e2b`, then `gemma4-e2b` — with
`gemma4-e2b-ocr` and `embeddinggemma-300m` in `rejected` as internal-only.

Also record measured tokens/sec for both chat models. If E2B is under ~8 tok/s on your machine,
L4's multi-step loop will be painful and you should say so in `PROGRESS.md` now, not at Session 8.

## Drift tripwires

- ❌ Editing `core/router.py`, `core/graph.py`, `core/kb.py`, `core/render.py`, `core/ingest.py`.
- ❌ Deleting the vLLM manifests. Disable them.
- ❌ Renaming `vram_gb`, or removing any frozen field.
- ❌ Adding an inference-engine abstraction layer. One function with three branches.
- ❌ Adopting Needle without the probe numbers.
- ❌ Installing the Cactus Flutter/React Native SDK. Wrong platform for a Python backend.
- ❌ Implementing model swapping or Sleep Mode. Everything is resident.

## Session exit

`PROGRESS.md`: the probe result for `structured_output_mode`, measured tok/s per model, the
768-dim note for L6, the Needle go/no-go, and
`## Next action: Session 4 — L5 Tool & Sandbox Plane`
