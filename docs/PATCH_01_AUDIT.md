# PATCH 01 — Audit Fixes (run before Session 4)

## MISSION LOCK

**Build:** nine specific defect fixes found in an external audit of the repo at Session 3.
Each has a named file, a named cause, and a regression test.

**You are NOT building:** any new layer, any new feature, any refactor beyond these nine items.
Do not "improve" adjacent code you happen to read.

**Files You Own:**
```
core/config.py
core/schemas.py
core/serving.py
core/router.py
.gitignore
pytest.ini
tests/test_schemas.py, tests/test_serving.py, tests/test_router.py
```

---

## P0-1 · `load_settings()` resolves against CWD

**Confirmed:** importing `core.config` from any directory other than the repo root raises
`FileNotFoundError`. Because `SETTINGS = load_settings()` runs at import, every module dies.

```python
# core/config.py
_REPO_ROOT = Path(__file__).resolve().parent.parent

def load_settings(path: str | Path | None = None) -> Settings:
    config_path = Path(path) if path is not None else _REPO_ROOT / "config.yaml"
    config_path = config_path if config_path.is_absolute() else (_REPO_ROOT / config_path)
    config_path = config_path.resolve()
    if not config_path.exists():
        raise WorkbenchError(f"config not found: {config_path}")
    ...
    base_dir = _REPO_ROOT          # ← anchor paths to the repo, never to CWD
```

Keep the explicit-`path` argument working for tests that pass a tmp config.

**Test:** `test_load_settings_works_from_any_cwd` — `monkeypatch.chdir(tmp_path)`, call
`load_settings()`, assert paths still resolve under the repo root.

## P0-2 · Directories are never created

**Confirmed:** `data/` does not exist. L3, L5, L6, L7b and L8 all write there.

At the end of `load_settings()`, before returning:
```python
for p in settings.paths.model_dump().values():
    Path(p).mkdir(parents=True, exist_ok=True)
```
`templates/` and `manifests/` are source dirs — creating them empty is harmless and prevents
the silent-empty-registry failure in P1-3.

**Test:** `test_load_settings_creates_directories(tmp_path)`.

## P0-3 · `.gitignore` drops L8's policy files

`policies/*.yaml` are **source**, not runtime state. As written they'd be untracked and lost
before the demo. Replace:
```
policies/*
!policies/.gitkeep
```
with:
```
# policies/ holds committed Tetragon TracingPolicy source — do NOT ignore it
```
Also add, ahead of Session 9:
```
data/signing_key.pem
*.pem
```
(`data/` already covers it, but be explicit — an accidentally committed signing key
invalidates every receipt you have ever issued.)

---

## P1-4 · OCR model competes for general vision routing

**Confirmed:** `capability_filter` on an image request returns
`['paddleocr-vl', 'qwen25-vl-7b']`. Arch-Router can route "what equipment is in this drawing?"
to an OCR extractor. Root cause: `RouteRequest.excluded_affinity` is a **single** value
defaulting to `ROUTING`, so OCR is never excluded.

Fix additively — do not remove any existing enum member or field.

```python
# core/schemas.py — ADD two members to TaskAffinity, remove none
class TaskAffinity(str, Enum):
    ...
    EMBEDDING = "embedding"            # NEW — embedding-only models
    OCR_EXTRACTION = "ocr_extraction"  # NEW — dedicated OCR/layout services
```

```python
# core/router.py
INTERNAL_ONLY_AFFINITIES = {
    TaskAffinity.ROUTING, TaskAffinity.EMBEDDING, TaskAffinity.OCR_EXTRACTION,
}

def _is_internal_only(m: ModelManifest) -> bool:
    """True when EVERY affinity is internal. A VLM that also drafts is not internal."""
    return set(m.task_affinities) <= INTERNAL_ONLY_AFFINITIES
```
Replace the `affinity` filter predicate with `lambda m, r: not _is_internal_only(m)`.
Keep `RouteRequest.excluded_affinity` in place (frozen contract) but stop relying on it.

Then edit `manifests/paddleocr-vl.yaml`: `task_affinities: [ocr_extraction]`.
Leave `qwen25-vl-7b` alone — it keeps `vision_extraction` alongside drafting, so it stays routable.

**Test:** `test_ocr_model_excluded_from_general_vision_routing` — image request, assert
`paddleocr-vl` appears in `rejected`, not in survivors.

## P1-5 · A router hiccup kills the task

`_arch_router_select` handles an invalid `model_id` but not an exception from
`complete_structured`. A router timeout propagates and dies. The L2 doc says the opposite.

Wrap the call:
```python
try:
    choice = await complete_structured(SETTINGS.router_model_id, messages, _ArchChoice)
except WorkbenchError as exc:
    logger.warning("router unavailable (%s); defaulting to first candidate", exc)
    return candidates[0].id, f"router unavailable ({type(exc).__name__}); defaulted to first candidate"
```
The fallback reason must stay human-readable — it renders in the R12 UI panel.

**Test:** `test_router_failure_falls_back_to_first_candidate` (monkeypatch
`complete_structured` to raise).

## P1-6 · `REGISTRY.get()` ignores `enabled`

**Confirmed:** `all()` filters on `enabled`; `get()` returns disabled manifests, so the kill
switch does nothing.

```python
def get(self, model_id: str, *, include_disabled: bool = False) -> ModelManifest:
    m = self._manifests.get(model_id)
    if m is None:
        raise WorkbenchError(f"unknown model_id: {model_id!r}")
    if not m.enabled and not include_disabled:
        raise WorkbenchError(f"model {model_id!r} is disabled in its manifest")
    return m
```
`manifest_hashes()` keeps returning all manifests — a receipt should record what was on disk.

Also make an empty registry loud. In `reload()`:
```python
if not manifests:
    logger.error("no manifests found in %s — every route will fail", self._manifests_dir)
```

**Test:** `test_get_disabled_model_raises`.

---

## P2-7 · Register the `integration` marker

A bare `pytest` currently goes red and burns 19 s retrying dead servers.
```ini
[pytest]
pythonpath = .
markers =
    integration: requires live model servers, Qdrant or Docker
addopts = -m "not integration"
```
With `addopts`, plain `pytest` is green by default and `pytest -m integration` opts in.

## P2-8 · `complete()` can return `None`

Typed `-> str`, but `message.content` is `str | None`.
```python
content = response.choices[0].message.content
if content is None:
    raise WorkbenchError(f"model {model_id!r} returned empty content")
return content
```
Same guard in `complete_structured` before `model_validate_json`.

## P2-9 · `EvidenceSpan.bbox` is unvalidated

`field_validator` is imported and unused — a validator was intended and dropped. Today
`EvidenceSpan(bbox=(5.0, -2.0, 900, 3), ...)` is accepted, and this is the atom of provenance
that L7b's fail-closed guarantee rests on.

```python
@field_validator("bbox")
@classmethod
def _bbox_normalised(cls, v):
    x0, y0, x1, y1 = v
    if not all(0.0 <= c <= 1.0 for c in v):
        raise ValueError(f"bbox must be normalised to [0,1], got {v}")
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"bbox must satisfy x0<x1 and y0<y1, got {v}")
    return v
```

**Test:** `test_evidence_span_rejects_unnormalised_bbox` and
`test_evidence_span_rejects_inverted_bbox`.

---

## Definition of Done

```bash
pytest -q                                    # green, fast, integration deselected
pytest -q -m integration                     # collects but skips/fails only on live services
cd /tmp && PYTHONPATH=<repo> python -c "from core.config import SETTINGS; print(SETTINGS.paths.data)"
python -c "
from core.router import capability_filter, RouteRequest
from core.schemas import TaskType, Modality
s, rej = capability_filter(RouteRequest(step_id='s1', task_type=TaskType.DOC_QA,
    instruction='What equipment is in this drawing?',
    required_modalities=[Modality.TEXT, Modality.IMAGE]))
print('survivors:', [m.id for m in s]); print('rejected:', rej)
"
```
The last command must print survivors `['qwen25-vl-7b']` only, with `paddleocr-vl` in `rejected`.

## Drift tripwires

- ❌ Removing or renaming any existing field or enum member in `core/schemas.py`. Additive only.
- ❌ Refactoring `serving.py` or `router.py` beyond these fixes.
- ❌ Building any part of L3, L4, L5, L6, L7 or L8.
- ❌ Deleting or weakening a failing test to make the suite green.

## Session exit

`PROGRESS.md`: which of the nine landed, DoD output pasted, and
`## Next action: PATCH 02 — local model profile (Gemma 4 / Ollama)`
