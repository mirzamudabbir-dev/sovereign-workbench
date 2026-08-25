# L2 — ROUTER

## MISSION LOCK

**Build:** automatic model selection. A deterministic capability filter, then Arch-Router-1.5B
for task fit, producing a fully-explained `RouteDecision`.

**You are NOT building:** the agent loop, prompts for tasks, model serving. You call
`core.serving.complete_structured()` and nothing else from outside your layer.

**Serves:** R3 (automatic selection based on task needs), R4 (new models routable with no
retraining and no code change), R12 (the demo).

**Files You Own:**
```
core/router.py
tests/test_router.py
```

---

## Why the filter exists (do not skip it)

Arch-Router selects on *task fit* — it is a preference model. It will happily hand a scanned
P&ID to a text-only model, or pick a model whose context is too short for the input. Those are
not preferences, they are **hard constraints**. So routing is two stages:

```
route(task_type, instruction, modalities, est_tokens, needs_grammar)
  ↓
  STAGE 1  capability filter   — deterministic, no LLM, eliminates the impossible
  ↓
  STAGE 2  Arch-Router-1.5B    — picks the best fit among survivors
  ↓
  RouteDecision                — every rejection recorded with a human-readable reason
```

`RouteDecision.rejected` is not diagnostics. It is the **UI panel judges will look at during
the R12 demo**. Populate it carefully, in plain English: `"qwen25-coder-7b: no image modality"`,
not `"filter_2_fail"`.

---

## `core/router.py` — required API

```python
"""L2 — automatic model selection. Filter first, then preference."""

CAPABILITY_FILTERS = [
    ("modality",   lambda m, r: set(r.required_modalities) <= set(m.modalities),
                   "does not support required modality: {mods}"),
    ("context",    lambda m, r: m.max_context >= r.estimated_tokens,
                   "context {ctx} < required {need} tokens"),
    ("grammar",    lambda m, r: (not r.needs_structured_output) or m.supports_grammar,
                   "does not support constrained decoding"),
    ("licence",    lambda m, r: m.licence_class in ALLOWED_LICENCES,
                   "licence class {lc} not permitted by org policy"),
    ("affinity",   lambda m, r: r.excluded_affinity not in m.task_affinities,
                   "reserved for internal use"),      # keeps router/OCR out of general routing
]

ALLOWED_LICENCES = {LicenceClass.PERMISSIVE, LicenceClass.RESTRICTED}


class RouteRequest(BaseModel):
    step_id: str
    task_type: TaskType
    instruction: str
    required_modalities: list[Modality] = [Modality.TEXT]
    estimated_tokens: int = 1024
    needs_structured_output: bool = False
    excluded_affinity: TaskAffinity = TaskAffinity.ROUTING


def capability_filter(req: RouteRequest) -> tuple[list[ModelManifest], dict[str, str]]:
    """Returns (survivors, rejected). Pure function, no I/O, fully unit-testable."""


async def route(req: RouteRequest) -> RouteDecision:
    """Full two-stage routing.

    - 0 survivors  -> raise WorkbenchError with the rejection table in the message.
    - 1 survivor   -> return it immediately, reason='only capable model', SKIP the LLM call.
    - 2+ survivors -> call Arch-Router.
    """


async def _arch_router_select(req, candidates: list[ModelManifest]) -> tuple[str, str]:
    """Build the route-policy prompt from candidate manifests, call Arch-Router with
    guided_json against _ArchChoice, return (model_id, reason)."""


class _ArchChoice(BaseModel):
    model_id: str
    reason: str = Field(max_length=200)


async def route_and_complete(req: RouteRequest, messages, *, schema_model=None,
                             images=None) -> tuple[str | BaseModel, RouteDecision]:
    """Convenience wrapper used by L4 for every LLM call. Routes, then dispatches to
    serving.complete() or serving.complete_structured(). Returns the result AND the
    decision so L4 can append it to the receipt."""
```

### The Arch-Router prompt

Built entirely from manifests — no hardcoded model knowledge:

```
You are a model router. Choose exactly one model for the request below.

AVAILABLE MODELS
- {id}: {description}          ← repeated per candidate, from the manifest
...

REQUEST TYPE: {task_type}
REQUEST: {instruction[:600]}

Reply with JSON: {"model_id": "...", "reason": "<20 words on why>"}
```

Validate that the returned `model_id` is in the candidate list. If not, fall back to the first
candidate with a reason of `"router returned invalid id; defaulted to first candidate"` and
log a WARNING. Never crash the task because the router hiccupped.

---

## Behaviour you must guarantee (these are the demo)

| Input | Expected chosen model | Why |
|---|---|---|
| "Summarise this inspection report" (text) | `qwen25-vl-7b` | affinity: summarisation |
| "Write a Python script to parse tag numbers" | `qwen25-coder-7b` | affinity: coding |
| "What equipment is shown in this drawing?" + image | `qwen25-vl-7b` | coder filtered out on modality |
| any request, 20 000 tokens | `qwen25-vl-7b` | coder filtered out on context (16 384) |

Write these four as tests. They are literally the R12 demo script.

---

## Tests — `tests/test_router.py`

```python
def test_filter_removes_text_only_model_for_image_request()
def test_filter_removes_short_context_model()
def test_filter_removes_non_grammar_model_when_structured_required()
def test_filter_excludes_router_and_ocr_from_general_routing()
def test_rejection_reasons_are_human_readable()      # assert no snake_case codes leak
def test_zero_survivors_raises_with_table()
async def test_single_survivor_skips_llm_call(monkeypatch)   # assert Arch-Router NOT called
def test_new_manifest_is_routable_without_code_change(tmp_path)   # ← R4 proof

@pytest.mark.integration
async def test_four_demo_routes()    # the table above
```

`test_new_manifest_is_routable_without_code_change`: add a manifest with affinity
`[general_reasoning]`, reload the registry, assert it appears in
`capability_filter(...)` survivors. No edits to `router.py` permitted for this to pass.

---

## Definition of Done

```bash
pytest tests/test_router.py -v -m "not integration"
python -c "
import asyncio; from core.router import route, RouteRequest
from core.schemas import TaskType, Modality
d = asyncio.run(route(RouteRequest(step_id='t.s1', task_type=TaskType.CODING,
    instruction='Write a Python function to parse P&ID tag numbers')))
print(d.model_dump_json(indent=2))
"
```
Output must show `chosen_model: qwen25-coder-7b`, a populated `rejected` dict, and a
human-readable `reason`.

## Drift tripwires

- ❌ Training, fine-tuning or "improving" the router model.
- ❌ RouteLLM, semantic-router, or any second routing library. Arch-Router only.
- ❌ Cost/latency optimisation, caching, or a bandit. Not required by any R.
- ❌ Data-classification-aware routing. Good idea, **not in the PS** — do not build it.
- ❌ Hardcoding model names in filter logic. All knowledge comes from manifests.
- ❌ Calling `openai` directly. Go through `core.serving`.

## Session exit

`PROGRESS.md`: the four demo routes and their actual outcomes.
`## Next action: L5 — core/sandbox.py + core/tools.py (needed before L4 can act)`
