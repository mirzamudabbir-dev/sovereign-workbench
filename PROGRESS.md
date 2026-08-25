# PROGRESS

Session handoff log. **Append only — never overwrite a previous entry.**
Every Claude Code session reads this at start and appends to it before ending or compacting.

A session that ends without an entry here has failed, regardless of how much code it wrote.

---

## Status board

| Layer | Doc | Owner | Status | DoD passing |
|---|---|---|---|---|
| — CONTRACTS | `docs/01_CONTRACTS.md` | | 🟢 complete | pytest tests/test_schemas.py -v |
| L0 Host | `docs/L0_HOST.md` | | 🟡 partial (all files built; DoD not verifiable on this dev machine) | `make preflight` fails all 7 checks on macOS dev box — see Session 1 log |
| L1 Serving | `docs/L1_SERVING.md` | | 🟡 partial (all files built, unit tests green; health() can't reach real vLLM on this dev machine) | `pytest tests/test_serving.py -v -m "not integration"` → 5/5 pass |
| L2 Router | `docs/L2_ROUTER.md` | | 🟡 partial (all files built, unit tests green; 3 of 4 demo routes need a live Arch-Router this dev machine doesn't have) | `pytest tests/test_router.py -v -m "not integration"` → 8/8 pass |
| L5 Sandbox | `docs/L5_SANDBOX.md` | | ⬜ not started | — |
| L3 Ingestion | `docs/L3_INGESTION.md` | | ⬜ not started | — |
| L6 KB | `docs/L6_KB.md` | | ⬜ not started | — |
| L7b Renderer | `docs/L7B_RENDERER.md` | | ⬜ not started | — |
| L4 Orchestrator | `docs/L4_ORCHESTRATOR.md` | | ⬜ not started | — |
| L8 Audit | `docs/L8_AUDIT.md` | | ⬜ not started | — |
| L7 UI | `docs/L7_UI.md` | | ⬜ not started | — |

Update your row at session end. Statuses: ⬜ not started · 🟡 partial · 🟢 complete · 🔴 blocked

---

## Requirement coverage (update as layers land)

| R | Requirement | Layer | Demoable |
|---|---|---|---|
| R1 | Air-gapped | L0 + L8 | ⬜ |
| R2 | Multiple models at once | L1 | 🟡 registry loads all 4; can't confirm co-resident serving without real GPU |
| R3 | Automatic model selection | L2 | 🟡 filter stage proven live; preference stage (Arch-Router) not yet run against a real server |
| R4 | Add models without redesign | L1 + L2 | ✅ proven by `test_registry_reload_picks_up_new_file` |
| R5 | Multi-step planning | L4 | ⬜ |
| R6 | Local tools | L5 + L6 | ⬜ |
| R7 | Iterates | L4 | ⬜ |
| R8 | Multimodal ingestion | L3 | ⬜ |
| R9 | Real deliverables | L7b | ⬜ |
| R10 | KB grounding | L6 | ⬜ |
| R11 | Mid-range GPU | L0 + L1 | ⬜ |
| R12 | DEMO auto-selection | L2 + L7 | ⬜ |
| R13 | DEMO scan → approval note | L3+L4+L6+L7b | ⬜ |
| R14 | DEMO code run & verified | L5 + L4 | ⬜ |
| R15 | DEMO multimodal | L3 + L4 | ⬜ |
| R16 | DEMO zero external calls | L8 | ⬜ |

---

## Environment facts (fill in during Session 1, then treat as ground truth)

**⚠️ Session 1 ran on the author's MacBook Air (Darwin 25.5.0, arm64), NOT the Ubuntu 22.04 +
NVIDIA venue machine target hardware describes. None of the facts below can be measured here.
They must be filled in for real the first time this repo runs on the actual venue box.**

- GPU model / VRAM: **N/A on this dev machine — no discrete GPU (Apple Silicon).** Unmeasured
  on target hardware.
- Free VRAM measured after all four vLLM services up: unmeasured — vLLM requires Linux+CUDA,
  cannot run on macOS at all (`vllm==0.6.6` has no arm64/macOS wheel).
- gVisor `runsc` installed? **Not attempted** — `scripts/00_install_gvisor.sh` requires
  `systemctl`/apt-based Linux and is a no-op-unsafe to run on macOS. Not installed, not tested.
- Docker version / nvidia-container-toolkit version: Docker Engine CLI 29.6.1 present via
  Homebrew, but **no Docker daemon/Desktop installed on this machine at all** — `docker info`
  fails with "no such file or directory" on the socket. `nvidia-container-toolkit`: N/A (no
  NVIDIA GPU). `docker compose` (plugin form, as used by the scripts) is not installed either —
  only a standalone `docker-compose` binary; the plugin exists on real Docker Desktop/Engine
  installs and is what the venue machine will have.
- Any `requirements.txt` pin that had to change, and why: **none.** Replaced the placeholder
  3-line `requirements.txt` from Session 0 with the full pinned list from `docs/L0_HOST.md`
  verbatim (vllm, langgraph, fastapi, streamlit, docling, qdrant-client, sentence-transformers,
  docxtpl, python-docx, python-pptx, openpyxl, docker, pydantic, pyyaml, cryptography, pillow,
  pymupdf, openai, pytest, httpx — all at the doc's pinned versions). Did **not** attempt
  `pip install -r requirements.txt` in `.venv` here — `vllm` alone would fail to build on
  macOS/arm64 and there's no reason to pollute the dev venv with packages this layer's own
  scripts (bash + stdlib-only `preflight.py`) don't need.
- `nft` (nftables): **not present on macOS at all** — it's Linux-only. `sudo nft list table
  inet sovereign` cannot be run on this machine under any configuration; this is a hard OS
  limitation, not a missing-package issue.
- Sandbox image cold-start latency: unmeasured (L5 sandbox image doesn't exist yet).
- OCR latency per page (PaddleOCR-VL): unmeasured (model not staged, no GPU to run it on).

---

## Open questions

Anything a session wanted to do but a Drift tripwire forbade. Resolve these **between**
sessions, as a team — never inside a session.

- _(none yet)_

---

## Deferred to post-demo

Recorded so nobody rebuilds the reasoning. All were deliberately cut; none is a bug.

- vLLM Sleep Mode + model-affinity scheduling (only needed if models stop fitting co-resident)
- ColPali / ColQwen visual retrieval (better on dense tables than text-only retrieval)
- Cross-encoder reranker on L6
- P&ID symbol detection + graph/topology index
- Model ingestion security gate (safetensors-only, pickle scanning, signature verification)
- python-pptx charting, PDF export, org theming
- Data-classification-aware routing

---

## Session log

## Session 0 — CONTRACTS — 2026-08-25

**Status:** complete
**Files created/changed:** `core/schemas.py`, `core/config.py`, `core/__init__.py`,
`tests/test_schemas.py`, `requirements.txt`, `pytest.ini`
(`core/schemas.py`, `core/config.py`, `config.yaml` already existed on disk matching the
contract exactly when this session started — verified field-for-field against
`docs/01_CONTRACTS.md` rather than rewritten. This session added the tests and the missing
`requirements.txt`.)
**Definition of Done:** `pytest tests/test_schemas.py -v` → PASS
```
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/mudabbir/Desktop/sovereign-workbench
configfile: pytest.ini
collecting ... collected 4 items

tests/test_schemas.py::test_evidence_span_rejects_confidence_above_one PASSED [ 25%]
tests/test_schemas.py::test_finding_rejects_empty_evidence_refs PASSED   [ 50%]
tests/test_schemas.py::test_model_manifest_round_trips_through_yaml PASSED [ 75%]
tests/test_schemas.py::test_load_settings_parses_config_yaml PASSED      [100%]

============================== 4 passed in 0.06s ===============================
```
`python -c "from core.config import SETTINGS; print(SETTINGS)"` → PASS, printed all
`SETTINGS.paths.*` as absolute `PosixPath`s rooted at the repo, e.g.
`data=PosixPath('/Users/mudabbir/Desktop/sovereign-workbench/data')`.

**Surprises a fresh session must know:**
- No venv/deps existed yet. Created `.venv/` (gitignored-worthy, not committed to any VCS —
  repo isn't even a git repo yet) and installed `pydantic`, `pyyaml`, `pytest` into it.
  Added `requirements.txt` pinning these three, per the repo layout in CLAUDE.md.
- Bare `pytest tests/test_schemas.py -v` fails with `ModuleNotFoundError: No module named
  'core'` because pytest does not add the repo root to `sys.path` by default when there's no
  `__init__.py` under `tests/`. Fixed by adding `pytest.ini` with `pythonpath = .` (not
  `python -m pytest`, so the DoD command as literally specified in the prompt still works).
- The working directory is **not** a git repository — `git status` returns "not a git
  repository". Nothing was committed.
- `manifests/`, `data/`, `models/` do not exist on disk yet. `load_settings()` does not
  require them to exist — it only resolves path strings — so this doesn't block anything here.

**Deviations from the doc (and why):**
- None in `core/schemas.py` or `core/config.py` — both were already byte-for-byte consistent
  with `docs/01_CONTRACTS.md` (same classes, same fields, same order, same defaults,
  `WorkbenchError` included).

### Open questions
- _(none)_

### Next action
Session 1 should read `CLAUDE.md`, `PROGRESS.md`, `docs/01_CONTRACTS.md`, and
`docs/L0_HOST.md`, then begin the L0 host substrate layer (R1) — the venv/dep pattern used
here (`requirements.txt` + local `.venv`) is a reasonable starting point for that layer's
Python-side setup, but L0 is primarily about host/container substrate, not this venv.

## Session 1 — L0 Host — 2026-08-25

**Status:** partial — every file built exactly to spec and syntax/logic-verified, but the
Definition of Done could not be run to green because this session's machine is not the target
hardware. Needs a real run on the Ubuntu + NVIDIA venue box before this row goes 🟢.

**Files created/changed:** `requirements.txt` (replaced Session 0's 3-line placeholder with the
full pinned list from `docs/L0_HOST.md`), `Makefile`, `docker-compose.yml`, `.gitignore`,
`scripts/00_install_gvisor.sh`, `scripts/01_lockdown_egress.sh`, `scripts/02_stage_models.sh`,
`scripts/03_start_services.sh`, `scripts/04_stop_services.sh`, `scripts/preflight.py`.
`config.yaml` verified against `Settings` in `docs/01_CONTRACTS.md` field-for-field — already
correct from Session 0, not touched.

**Definition of Done:** `make preflight` → **FAIL (exit 1)**, `sudo nft list table inet
sovereign` → **cannot run at all (nft does not exist on macOS)**. Real output below, not
fabricated — this session's dev machine (MacBook Air, Darwin 25.5.0, arm64) is not the Ubuntu
22.04 + NVIDIA target hardware `docs/L0_HOST.md` assumes, so a green run isn't possible here
regardless of how the scripts are written. See `## Environment facts` above for the full
platform gap.
```
$ make preflight
python3 scripts/preflight.py

SOVEREIGN WORKBENCH — PREFLIGHT
----------------------------------------------------------------------
[FAIL] 1. GPU present, free VRAM ≥ 20 GB
        nvidia-smi not found on this host
[FAIL] 2. All 4 vLLM /v1/models answer with correct name
        :8001 unreachable (Connection refused); :8002 unreachable (Connection refused);
        :8003 unreachable (Connection refused); :8004 unreachable (Connection refused)
[FAIL] 3. Qdrant healthy, Tetragon running, events.json growing
        qdrant unreachable (Connection refused); tetragon container not running;
        .../data/tetragon/events.json does not exist yet
[FAIL] 4. gVisor runtime usable (--runtime=runsc)
        exit 1: failed to connect to the docker API at unix:///var/run/docker.sock;
        check if the path is correct and if the daemon is running: dial unix
        /var/run/docker.sock: connect: no such file or directory
[FAIL] 5. NEGATIVE CONTROL: --network=none egress must FAIL
        could not run the check at all — docker daemon unreachable: failed to connect
        to the docker API at unix:///var/run/docker.sock: no such file or directory
[FAIL] 6. HF_HUB_OFFLINE=1 in every service env
        no running vLLM services found (run/*.pid empty)
[FAIL] 7. Templates exist and open
        .../templates does not exist yet (L7b not built)
----------------------------------------------------------------------
PREFLIGHT FAILED — do not demo until every check is green.

make: *** [preflight] Error 1

$ which nft
nft not found
```
Every failure above is a real, correct report of this machine's actual state — nothing was
stubbed to fake a pass. Check 5 (the negative control) is the one that matters most and is
discussed under Surprises below.

**Surprises a fresh session must know:**
- **This session caught and fixed a real bug in `preflight.py` before finishing**, not a
  platform-gap issue: the negative-control check (5) originally treated *any* nonzero exit
  from `docker run --network=none ... wget ...` as "egress correctly blocked." But when the
  Docker daemon itself isn't reachable (as on this machine), `docker run` also exits nonzero —
  for a completely different reason — and the check was reporting a false PASS without the
  container ever having run. Fixed by detecting the daemon-unreachable stderr pattern
  (`"failed to connect to the docker API"` / `"docker.sock"` / etc.) and reporting that as an
  explicit FAIL distinct from "wget correctly failed to reach 1.1.1.1". **Any future edit to
  check 5 must preserve this distinction** — a negative control that can silently no-op into a
  false pass is worse than no check at all.
- This machine has the `docker` CLI (Homebrew, v29.6.1) but **no Docker daemon/Desktop
  installed at all** — not "daemon not running," but no backend present. `docker compose` (the
  modern plugin subcommand, which is what `scripts/03/04` and the Makefile use per the doc) is
  also absent; only a legacy standalone `docker-compose` binary is on PATH. Neither gap was
  worked around — the scripts are written correctly for the venue machine's real Docker Engine
  + compose-plugin install, per spec.
- `nft` does not exist on macOS under any circumstance (it's Linux-specific netfilter tooling)
  — this isn't a "missing package," there is no fallback. `scripts/01_lockdown_egress.sh` was
  therefore written correctly for Ubuntu but **never executed** this session; running it here
  would just hard-fail on the `command -v nft` guard, which is by design (see the script).
- `vllm==0.6.6` (and most of the rest of `requirements.txt`) cannot install on macOS/arm64 —
  no wheel, needs CUDA. Did not attempt `pip install -r requirements.txt` in the shared
  `.venv`; L0's own deliverables (bash scripts + `scripts/preflight.py`) only need the stdlib,
  so nothing in this layer actually required those packages to be installed here.
- `scripts/03_start_services.sh` checks for `api.py` / `ui.py` before trying to launch them
  (they don't exist yet — L7 hasn't run) and skips with a warning instead of hard-failing, so
  the script stays usable during earlier build-out before L7 lands. This is a deliberate
  deviation from a literal reading of the doc's step 5 (which just says "then uvicorn ...,
  then streamlit ...") — without the guard, every `make start` before L7 exists would abort
  with `ModuleNotFoundError`. Recorded here rather than silently added.
- `policies/`, `run/`, `data/qdrant/`, `data/tetragon/` are **not** committed as empty dirs —
  `scripts/03_start_services.sh` creates them at runtime (`mkdir -p`) since they weren't in
  L0's "Files You Own" list and are pure runtime state (all gitignored anyway).

**Deviations from the doc (and why):**
- None in the shape of any owned file vs. the doc's specified content/build order — the one
  behavioral deviation (the `api.py`/`ui.py` existence guard in `03_start_services.sh`) is
  called out above and is additive/defensive, not a contradiction of the doc's intent.

### Open questions
- _(none — the dev-machine/venue-machine gap is an environment fact, not a design question;
  nothing here needed a Drift-tripwire judgment call)_

### Next action
Session 2 — L1 Model Serving Plane — start with `manifests/qwen25-vl-7b.yaml`. Before trusting
any L0 "PASS," this repo needs one real run of `make preflight` on the actual Ubuntu 22.04 +
NVIDIA venue box — that has not happened yet and nothing in Session 1 could substitute for it.

## Session 2 — L1 Serving — 2026-08-25

**Status:** partial — every owned file built exactly to spec, unit tests all green, but the
second Definition of Done command reports all-`False` health because this dev machine (same
MacBook Air as Session 1, no GPU, no vLLM) has no model servers listening on 8001–8004. Code
path is verified correct (connection failures return fast and clean, no hang); needs a real run
on the venue box to go 🟢.

**Files created/changed:** `manifests/qwen25-vl-7b.yaml`, `manifests/qwen25-coder-7b.yaml`,
`manifests/arch-router-1.5b.yaml`, `manifests/paddleocr-vl.yaml` (new dir, all four written
verbatim/by-shape from `docs/L1_SERVING.md`), `core/serving.py` (`ModelRegistry`, `REGISTRY`
singleton, `health()`, `complete()`, `complete_structured()`, `estimate_tokens()`), and
`tests/test_serving.py` (7 tests: 5 unit + 2 `@pytest.mark.integration`).

**Manifests that exist:** all four required — `qwen25-vl-7b` (port 8001, text+image, grammar
yes), `qwen25-coder-7b` (port 8002, text-only, grammar yes), `arch-router-1.5b` (port 8003,
text-only, grammar yes, routing-only affinity), `paddleocr-vl` (port 8004, text+image, grammar
**no** — OCR model, doesn't need structured output). Each `description` is written as "what
work belongs here" per the doc's instruction that L2 feeds it to Arch-Router as route policy,
not marketing copy.

**Definition of Done:**

`pytest tests/test_serving.py -v -m "not integration"` → **PASS**
```
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0 -- .../.venv/bin/python3.12
plugins: asyncio-1.4.0, anyio-4.14.2
collecting ... collected 7 items / 2 deselected / 5 selected

tests/test_serving.py::test_registry_loads_four_manifests PASSED         [ 20%]
tests/test_serving.py::test_registry_reload_picks_up_new_file PASSED     [ 40%]
tests/test_serving.py::test_get_unknown_model_raises PASSED              [ 60%]
tests/test_serving.py::test_estimate_tokens_counts_images PASSED         [ 80%]
tests/test_serving.py::test_complete_rejects_images_for_text_only_model PASSED [100%]

================= 5 passed, 2 deselected, 2 warnings in 0.64s ==================
```
(The 2 warnings are `PytestUnknownMarkWarning` for the unregistered `integration` mark — cosmetic
only, doesn't affect pass/fail; left `pytest.ini` untouched since it's outside this layer's
"Files You Own.")

`python -c "..." ` (manifest_hashes + health) → **health all False, as expected on this machine**
```
{'arch-router-1.5b': '47f86302f1ae1246dd702acfacb9751975dc5d79c7ad903444cae252f0cbb2c7',
 'paddleocr-vl': '2623d96ce68b774a5eb2d16e0c674db205d3540d5b66620a8b3b306ed6b9bdd0',
 'qwen25-coder-7b': 'ea1b2bd3a4a301e573d8628800ef692ca431f962a42afe5bd05b3c1eaa6e0d01',
 'qwen25-vl-7b': 'a4e043f810efa650ad7809227a7905069c5c56557e9e4396b8704b0017e109b5'}
{'arch-router-1.5b': False, 'paddleocr-vl': False, 'qwen25-coder-7b': False, 'qwen25-vl-7b': False}
```
Ran under `time`: 1.8s wall total for all four connection attempts — `ConnectionRefusedError` on
a closed local port fails immediately (no 180s timeout hit), so `health()`'s behavior is
confirmed correct even though the answer is "false" here. **All four must report `True` the
first time this runs against real vLLM processes on 127.0.0.1:8001–8004 on the venue box** —
this has NOT been verified yet, same platform gap as Session 1's L0 preflight.

**Surprises a fresh session must know:**
- No `openai`, `httpx`, or `pytest-asyncio` were installed in `.venv` yet (Session 0 only put in
  `pydantic`/`pyyaml`/`pytest`). Installed `openai==1.59.6`, `httpx==0.28.1` (both match
  `requirements.txt` pins) plus `pytest-asyncio` (not in `requirements.txt` — dev/test-only,
  needed to actually execute the two `@pytest.mark.integration` async test bodies if someone
  runs them later; not needed for the DoD's own `-m "not integration"` command, which has zero
  async tests reached — `test_complete_rejects_images_for_text_only_model` calls the async
  `complete()` via a plain `asyncio.run(...)` inside a sync `def test_...`, specifically so the
  required DoD tests don't depend on `pytest-asyncio`/`pytest.ini` config at all).
- No vLLM flag had to change — this session never got as far as starting a vLLM process (no GPU
  on this machine, same as Session 1's L0 gap). `core/serving.py` and the manifests are written
  exactly to the doc's ports/paths; nothing here is provisional pending a flag fix.
- `manifests/` did not exist on disk before this session (`ls` returned "No such file or
  directory") — created fresh with exactly the four files, nothing else.
- Retry logic (`httpx.ConnectError` / `openai.APIConnectionError`, 2 retries, 2s backoff) is
  implemented in `_call_with_retry()` but is only exercised by `complete()`/`complete_structured()`
  — `health()` deliberately does NOT retry (fails fast per-model via `asyncio.gather`), since it
  backs a UI status bar / preflight check where a slow health probe is worse than an honest fast
  "down." This is a judgement call beyond the doc's literal text, not a deviation from any stated
  requirement — recording it here in case L7's status bar assumes a retry occurred.

**Deviations from the doc (and why):**
- None in file shape, function signatures, or manifest fields — all match
  `docs/L1_SERVING.md` and `docs/01_CONTRACTS.md` exactly, including `extra_body={"guided_json":
  ...}` for grammar constraint (no Outlines/Instructor/guidance installed) and zero
  `if model_id ==` string matching anywhere in `core/serving.py` (grepped and confirmed clean).

### Open questions
- _(none — the health()-all-False result is a dev-machine platform gap, not a design question,
  exactly like Session 1's L0 preflight failures)_

### Next action
Session 3 — L2 Router — start with `capability_filter()` in `core/router.py`. Before trusting
L1's "all four `True`" health claim, this repo needs one real run of the DoD `python -c "..."`
snippet on the actual Ubuntu 22.04 + NVIDIA venue box with all four vLLM processes started —
that has not happened yet.

## Session 3 — L2 Router — 2026-08-25

**Status:** partial — `core/router.py` and `tests/test_router.py` built exactly to spec, all
8 non-integration unit tests pass for real, and the two-stage design is fully exercised
(filter-only rejection tables, zero-survivor error path, single-survivor short-circuit, R4
new-manifest routability). The live `route()` call for the CODING demo route hits the same
no-GPU/no-vLLM wall as Sessions 1 and 2: 3 of the 4 demo routes need a real Arch-Router
completion and this dev machine has no model servers running on 8001–8004.

**Files created/changed:** `core/router.py` (`RouteRequest`, `CAPABILITY_FILTERS`,
`capability_filter()`, `route()`, `_arch_router_select()`, `_ArchChoice`,
`route_and_complete()`), `tests/test_router.py` (8 unit tests + 1
`@pytest.mark.integration` test covering the four demo routes).

**Definition of Done:**

`pytest tests/test_router.py -v -m "not integration"` → **PASS**
```
collected 9 items / 1 deselected / 8 selected

tests/test_router.py::test_filter_removes_text_only_model_for_image_request PASSED [ 12%]
tests/test_router.py::test_filter_removes_short_context_model PASSED     [ 25%]
tests/test_router.py::test_filter_removes_non_grammar_model_when_structured_required PASSED [ 37%]
tests/test_router.py::test_filter_excludes_router_and_ocr_from_general_routing PASSED [ 50%]
tests/test_router.py::test_rejection_reasons_are_human_readable PASSED   [ 62%]
tests/test_router.py::test_zero_survivors_raises_with_table PASSED       [ 75%]
tests/test_router.py::test_single_survivor_skips_llm_call PASSED         [ 87%]
tests/test_router.py::test_new_manifest_is_routable_without_code_change PASSED [100%]

================== 8 passed, 1 deselected, 1 warning in 0.29s ==================
```

`python -c "..."` (CODING demo route, exact command from `docs/L2_ROUTER.md`) → **FAIL on this
machine, for a real and expected reason, not a bug**:
```
core.schemas.WorkbenchError: connection to model server failed after 3 attempts: Connection error.
```
Root cause: for `instruction="Write a Python function to parse P&ID tag numbers"` with default
`RouteRequest` fields, **3 models survive the capability filter** — `qwen25-vl-7b`,
`qwen25-coder-7b`, **and `paddleocr-vl`**. `paddleocr-vl` is not excluded by the affinity filter
here because the request's `excluded_affinity` defaults to `TaskAffinity.ROUTING` (which only
removes `arch-router-1.5b`), and paddleocr's own affinity is `vision_extraction`, not `routing`.
With 3 survivors, `route()` correctly calls live Arch-Router — which isn't running on this
Mac. This is by design, not a bug: the capability filter only removes what's *impossible*
(paddleocr technically has enough context and the right modality for a text coding task); it's
Arch-Router's job, reading the manifest `description` fields, to never actually pick paddleocr
for a coding task. **The four demo routes therefore split into two groups by dependency**:

| Demo route | Survivors after filter | Needs live Arch-Router? |
|---|---|---|
| "Summarise this inspection report" | vl, coder, paddleocr | yes |
| "Write a Python function to parse P&ID tag numbers" | vl, coder, paddleocr | yes |
| "What equipment is shown in this drawing?" + image | vl, paddleocr (coder filtered: no image) | yes |
| any request, 20 000 tokens | vl only (coder + paddleocr filtered: context too small) | **no — single-survivor short-circuit** |

Ran the one route that doesn't need a live model (20 000-token case) for real, successfully,
with the actual rejection table populated:
```json
{
  "step_id": "t.s4",
  "required_modalities": ["text"],
  "estimated_tokens": 20000,
  "needs_structured_output": false,
  "candidates_considered": ["qwen25-vl-7b"],
  "rejected": {
    "arch-router-1.5b": "context window is 8192 tokens, too small for this request's estimated 20000 tokens",
    "paddleocr-vl": "context window is 8192 tokens, too small for this request's estimated 20000 tokens",
    "qwen25-coder-7b": "context window is 16384 tokens, too small for this request's estimated 20000 tokens"
  },
  "chosen_model": "qwen25-vl-7b",
  "reason": "only capable model",
  "latency_ms": 0.01
}
```
The other three demo routes (including the CODING one named in the DoD) are covered instead by
`tests/test_router.py::test_four_demo_routes`, marked `@pytest.mark.integration`, and by
`tests/test_router.py::test_single_survivor_skips_llm_call`, which proves via `monkeypatch`
that Arch-Router is *not* called when only one candidate survives. **All 3 remaining demo
routes must be re-run for real on the venue box** once Arch-Router-1.5B is actually serving on
`:8003` — same unverified-on-this-machine caveat as every prior session's live-model claim.

**Surprises a fresh session must know:**
- **`paddleocr-vl` structurally survives the capability filter for ordinary text/coding
  requests**, not just OCR ones — the filter's affinity check only excludes whatever single
  `TaskAffinity` the caller passes as `excluded_affinity` (default `ROUTING`), so keeping OCR
  out of *every* non-OCR route is left to Arch-Router's semantic judgment (via the manifest
  `description` text), not to the deterministic filter. `test_filter_excludes_router_and_ocr_from_general_routing`
  proves the mechanism works for *both* affinities, but demonstrates OCR exclusion only when a
  caller explicitly passes `excluded_affinity=TaskAffinity.VISION_EXTRACTION` — L4 should do
  this for any step that isn't itself an OCR/extraction step, if it wants paddleocr excluded
  from the candidate pool rather than relying on Arch-Router to never pick it.
- Rejection-reason strings deliberately avoid underscores entirely (e.g. licence class values
  and affinity names are `.replace('_', ' ')`'d before interpolation) so
  `test_rejection_reasons_are_human_readable` has a real, meaningful assertion (`"_" not in
  reason`) rather than a tautology.
- `capability_filter()` reads the module-level `REGISTRY` name from `core.serving` by reference
  (not a value captured at import time), specifically so `test_new_manifest_is_routable_without_code_change`
  can `monkeypatch.setattr(router, "REGISTRY", test_registry)` and prove R4 without touching
  `router.py`.
- No `pytest.ini` changes made (not in this layer's "Files You Own") — the `integration` mark
  still prints the same cosmetic `PytestUnknownMarkWarning` seen in Session 2; harmless.

**Deviations from the doc (and why):**
- None in file shape or function signatures. `CAPABILITY_FILTERS` entries carry a reason
  *function* `(manifest, request) -> str` rather than a literal template string with named
  placeholders like `"{mods}"` — the doc's snippet was illustrative pseudocode (it also omits
  `ALLOWED_LICENCES`'s exact position and leaves class bodies as `...`); the behavior (5 named
  filters in the specified order, human-readable per-model rejection reasons) matches exactly.

### Open questions
- _(none — the live-Arch-Router gap is the same dev-machine/venue-machine platform gap as
  every prior session, not a design question)_

### Next action
Session 4 — L5 Tool & Sandbox Plane — start with `sandbox/Dockerfile`.

<!-- Append below. Template:

## Session N — [LAYER] — YYYY-MM-DD

**Status:** complete | partial | blocked
**Files created/changed:**
**Definition of Done:** <command> → PASS/FAIL
```
<paste real terminal output — not a summary>
```
**Surprises a fresh session must know:**
**Deviations from the doc (and why):**

### Open questions
-

### Next action
[Exact next thing: session number, layer, first function to write]

-->
