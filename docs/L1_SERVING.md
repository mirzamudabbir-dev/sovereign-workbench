# L1 — MODEL SERVING PLANE

## MISSION LOCK

**Build:** the model registry (YAML manifests → `ModelManifest`) and a single async client that
every other layer uses to talk to any model, including grammar-constrained JSON output.

**You are NOT building:** the routing *decision* (that is L2 — you expose the candidate list and
the call mechanism; L2 chooses). No agent loop, no prompts about inspection reports, no UI.

**Serves:** R2 (multiple models at once), R4 (add models without redesign), R11 (fits one GPU).

**Files You Own:**
```
core/serving.py
manifests/qwen25-vl-7b.yaml
manifests/qwen25-coder-7b.yaml
manifests/arch-router-1.5b.yaml
manifests/paddleocr-vl.yaml
tests/test_serving.py
```

**Files You May NOT Touch:** `core/router.py`, `core/graph.py`, anything else in `core/`.
`core/schemas.py` is read-only to you.

---

## The R4 property — read this before writing code

> **Adding a new open-weight model must require exactly two actions: (1) drop the weights on
> disk and start a vLLM process, (2) drop a YAML file in `manifests/`. Zero Python edits.**

Everything in this layer exists to make that sentence true. If you write `if model_id == "..."`
anywhere, you have broken R4. There are no model-specific code paths in `core/serving.py`.

---

## Manifests

One file per model, parsed into `ModelManifest` (see `docs/01_CONTRACTS.md`).

`manifests/qwen25-vl-7b.yaml`:
```yaml
id: qwen25-vl-7b
served_model_name: Qwen/Qwen2.5-VL-7B-Instruct-AWQ
base_url: http://127.0.0.1:8001/v1
licence_class: permissive
modalities: [text, image]
max_context: 32768
vram_gb: 6.7
quantization: awq
supports_grammar: true
task_affinities: [drafting, summarisation, general_reasoning, vision_extraction]
description: >
  General-purpose reasoning and drafting model that can also read images. Use for writing
  approval notes, summarising reports, answering questions about documents, and any request
  that includes a picture, scan, or engineering drawing.
enabled: true
```

`manifests/qwen25-coder-7b.yaml`:
```yaml
id: qwen25-coder-7b
served_model_name: Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
base_url: http://127.0.0.1:8002/v1
licence_class: permissive
modalities: [text]
max_context: 16384
vram_gb: 4.8
quantization: awq
supports_grammar: true
task_affinities: [coding]
description: >
  Specialised code model. Use for writing, fixing, refactoring or explaining source code,
  writing scripts, generating engineering calculations as executable Python, and producing
  test cases.
enabled: true
```

`arch-router-1.5b` (affinity `[routing]`, modalities `[text]`, `supports_grammar: true`) and
`paddleocr-vl` (affinity `[vision_extraction]`, modalities `[text, image]`,
`supports_grammar: false`) follow the same shape.

**`description` is load-bearing** — L2 feeds it to Arch-Router as the route policy. Write it as
a description of *what work belongs here*, not as marketing copy about the model.

---

## `core/serving.py` — required API

```python
"""L1 — model registry + unified inference client. No routing decisions here."""

class ModelRegistry:
    def __init__(self, manifests_dir: Path): ...
    def reload(self) -> None:
        """Re-read every *.yaml in manifests_dir. Called at startup and by /admin/reload."""
    def all(self) -> list[ModelManifest]:
        """Enabled manifests only."""
    def get(self, model_id: str) -> ModelManifest:
        """Raise WorkbenchError if unknown."""
    def manifest_hashes(self) -> dict[str, str]:
        """model_id -> sha256 of the manifest file. Consumed by L8 receipts."""

REGISTRY = ModelRegistry(SETTINGS.paths.manifests)   # module singleton


async def health() -> dict[str, bool]:
    """GET {base_url}/models for every manifest. Verify served_model_name is present.
    Used by preflight and the UI status bar."""


async def complete(
    model_id: str,
    messages: list[dict],
    *,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    images: list[Path] | None = None,
) -> str:
    """Free-text completion. `images` are base64-inlined as image_url content parts.
    Raise WorkbenchError if the manifest lacks Modality.IMAGE but images were passed."""


async def complete_structured(
    model_id: str,
    messages: list[dict],
    schema_model: type[BaseModel],
    *,
    max_tokens: int = 4096,
    images: list[Path] | None = None,
) -> BaseModel:
    """Grammar-constrained generation via vLLM's native guided_json (XGrammar backend).

    extra_body={"guided_json": schema_model.model_json_schema()}

    Then schema_model.model_validate_json(...). On ValidationError, retry ONCE with the
    validation error appended as a user message, then raise WorkbenchError.
    Raise immediately if manifest.supports_grammar is False.
    """


def estimate_tokens(messages: list[dict], images: list[Path] | None = None) -> int:
    """len(text)//3.5 + 800 per image. Deliberately crude — L2 only needs it to filter
    models by max_context, not to bill anyone."""
```

Implementation notes:
- One `openai.AsyncOpenAI(base_url=..., api_key="EMPTY")` per manifest, created lazily, cached
  in a module dict keyed by `model_id`.
- Timeout 180 s. Retry `httpx.ConnectError` twice with 2 s backoff, then raise.
- Log every call at INFO: `model_id`, token estimate, latency, ok/fail. L8 does not read these
  logs; they are for you.
- **No prompt templates in this file.** Prompts belong to the layer that owns the task.

---

## Tests — `tests/test_serving.py`

```python
def test_registry_loads_four_manifests()
def test_registry_reload_picks_up_new_file(tmp_path)     # ← this test IS R4
def test_get_unknown_model_raises()
def test_estimate_tokens_counts_images()
def test_complete_rejects_images_for_text_only_model()

@pytest.mark.integration     # requires services up
async def test_health_all_green()
async def test_complete_structured_returns_valid_model()  # tiny 2-field schema
```

`test_registry_reload_picks_up_new_file` must: write a fifth YAML to a tmp manifests dir,
call `reload()`, assert `len(all()) == 5` — **with no other code change**. That test is the
executable proof of R4 and you will demo it.

---

## Definition of Done

```bash
pytest tests/test_serving.py -v -m "not integration"   # all pass
python -c "
import asyncio
from core.serving import health, REGISTRY
print(REGISTRY.manifest_hashes())
print(asyncio.run(health()))
"   # → all four True
```

## Drift tripwires

- ❌ Any `if model_id ==` or model-name string matching.
- ❌ Installing Outlines / Instructor / guidance. Use `extra_body={"guided_json": ...}`.
- ❌ Installing LiteLLM or building a "gateway". A dict of clients is the gateway.
- ❌ Implementing Sleep Mode, model swapping, or a load balancer. All four models are resident.
- ❌ Writing a prompt about inspection reports, approval notes, or P&IDs in this file.
- ❌ Choosing which model to use. That is L2's job — you only expose `all()` and `complete()`.

## Session exit

`PROGRESS.md`: which manifests exist, health results, any vLLM flag that had to change.
`## Next action: L2 — core/router.py (capability filter + Arch-Router)`
