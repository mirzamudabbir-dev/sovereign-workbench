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
| L1 Serving | `docs/L1_SERVING.md` | | 🟢 local (Ollama) profile fully live on this machine — health(), complete(), complete_structured() all verified against real models (see PATCH 02 below); 🟡 vLLM/demo-box profile still unverified — needs the venue Ubuntu+NVIDIA box | `pytest tests/test_serving.py -v` → 13/13 pass (11 unit + 2 integration, all real) |
| L2 Router | `docs/L2_ROUTER.md` | | 🟢 unit tests profile-agnostic and green under both manifest profiles; live demo-route integration test passes for real on this machine (Ollama profile) — see PATCH 03 | `pytest tests/test_router.py -v` → 10/10 pass (9 unit + 1 integration, all real) |
| L5 Sandbox | `docs/L5_SANDBOX.md` | | 🟢 complete — real gVisor (`runsc`), real Docker, all DoD commands genuinely green on this dev machine (see Session 4) | `pytest tests/test_sandbox.py -v` → 23/23 pass, real containers, no mocks |
| L3 Ingestion | `docs/L3_INGESTION.md` | | 🟢 complete — native (Docling) and scanned/image (live OCR) paths both proven for real on this machine, including the V-101 regression test (see Session 5) | `pytest tests/test_ingest.py -v` → 9/9 pass (8 unit + 1 integration deselected by default); `-m integration` → 1/1 pass live |
| L6 KB | `docs/L6_KB.md` | | 🟢 complete — real Qdrant (Docker/colima), real embedding calls, all live on this machine (see Session 6) | `pytest tests/test_kb.py -v -m integration` → 10/10 pass, real services, no mocks |
| L7b Renderer | `docs/L7B_RENDERER.md` | | 🟢 complete — all 14 tests real, no live services needed (see Session 7) | `pytest tests/test_render.py -v` → 14/14 pass |
| L4 Orchestrator | `docs/L4_ORCHESTRATOR.md` | | 🟡 partial — code complete, 7/7 non-integration tests pass for real; live end-to-end demos NOT completed this session (thermal/time constraints on this dev machine, see Session 8) | `pytest tests/test_graph.py -v -m "not integration"` → 7/7 pass. `--demo coding`/`--demo approval` not yet run to completion. |
| L8 Audit | `docs/L8_AUDIT.md` | | 🟢 complete — **all 34 tests pass (32 non-integration + 2 integration), the full test suite finished**; `--demo doc_qa` (added to L4 with user sign-off) runs end-to-end producing a real receipt that verifies ✅ SOVEREIGN; a real Tetragon container (via colima) proved live kernel-level observation AND enforcement (a genuine SIGKILL); a real bug in the doc's own `egress_observe.yaml` (a NotDAddr filter that made internal-connection capture structurally impossible) found and fixed — see Session 9 (continued x2). Only one continuous unbroken `negative_control.sh` run is outstanding, blocked by this 8 GB dev machine's resource limits under colima+Tetragon+Qdrant+Ollama simultaneously, not a code defect. | `pytest tests/test_receipt.py -v` (both marks) → 34/34 pass; `verify_receipt.py` on a real receipt → exit 0 ✅ SOVEREIGN |
| L7 UI | `docs/L7_UI.md` | | ⬜ not started | — |

Update your row at session end. Statuses: ⬜ not started · 🟡 partial · 🟢 complete · 🔴 blocked

---

## Requirement coverage (update as layers land)

| R | Requirement | Layer | Demoable |
|---|---|---|---|
| R1 | Air-gapped | L0 + L8 | 🔴 **a real, live violation was found and confirmed this session** — running the test suite on this dev machine opens a genuine outbound HTTPS connection to an Amazon CloudFront IP (Docling's model-loading path checking HuggingFace Hub for updates), because `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` are not set anywhere in this project's dev/test environment. Confirmed reproducible, confirmed root-caused, confirmed fixed by setting those two env vars (tests still pass identically). Not patched by this session — it is not L8's file to fix — see Session 9 and Open Questions below. L8's own receipt/signing machinery is otherwise proven correct: it is exactly the kind of event a real Tetragon/pktap capture would have caught and flagged in a receipt. |
| R2 | Multiple models at once | L1 | 🟡 registry loads all 4, all 4 individually healthy live (Ollama profile). Co-residency is *technically* achievable (observed once, real) but is memory-pressure-dependent and causes heavy swapping on this 8 GB machine — this profile deliberately runs **sequential-with-reload**, not co-resident. See PATCH 04: root cause found (`gemma4:e2b`'s true footprint is ~6.5 GB, not 1.7 GB), reload cost measured (~9.3 s median for gemma) |
| R3 | Automatic model selection | L2 | ✅ proven live end-to-end on the local profile — all 3 non-trivial demo routes (coding / text-QA / image-QA) ran against real `gemma4-e2b` acting as router and chose correctly; see PATCH 02 |
| R4 | Add models without redesign | L1 + L2 | ✅ proven by `test_registry_reload_picks_up_new_file` |
| R5 | Multi-step planning | L4 | ✅ proven live end-to-end: `--demo doc_qa` really calls the LLM for a structured plan per task type (no hardcoded pipeline), real plans generated across 3 re-plan iterations in one recorded run — see Session 9 (continued) |
| R6 | Local tools | L5 + L6 | ✅ all four tool families (fs, code, sheet; kb.search delegates and correctly fails loudly since L6 doesn't exist yet) proven live against a real gVisor container — see Session 4 |
| R7 | Iterates | L4 | ✅ proven live end-to-end: a real `--demo doc_qa` run genuinely iterated 3 times (`verify -> plan` loop) on a real, unprompted LLM planning shortfall, then correctly escalated to APPROVE at `SETTINGS.agent.max_iterations` — not simulated, the actual DOC_QA plan kept omitting an llm_call step and the loop caught it each time. See Session 9 (continued); also unit-tested (`test_verify_failure_routes_back_to_plan`, `test_iteration_budget_forces_escalation`). |
| R8 | Multimodal ingestion | L3 | ✅ proven live: native PDF → Docling text-layer extraction, scanned PDF → real OCR model with the literal tag V-101 recovered verbatim, engineering drawing PNG → real OCR with tag PSV-2204 recovered — see Session 5. Handwriting itself is *not* demonstrated (no handwriting fixture in scope); `needs_review` gating is proven only via a synthetic unit test, not a live low-confidence sample. |
| R9 | Real deliverables | L7b | ✅ proven live: `render()` produced a real .docx (37.5KB, populated provenance appendix), .pptx (34.4KB, 6 slides), and .xlsx (6.7KB, 3 sheets) from one sample plan, all open cleanly via python-docx/python-pptx/openpyxl — see Session 7 |
| R10 | KB grounding | L6 | ✅ proven live: `scripts/index_corpus.py` really ingested all 3 `tests/fixtures` documents (native PDF, scanned PDF, drawing PNG) and indexed 21 real spans into a real Qdrant; `search("V-101 minimum thickness")` returns the literal-tag span (`matched_by="both"`) — see Session 6 |
| R11 | Mid-range GPU | L0 + L1 | ⬜ |
| R12 | DEMO auto-selection | L2 + L7 | ⬜ |
| R13 | DEMO scan → approval note | L3+L4+L6+L7b | ⬜ |
| R14 | DEMO code run & verified | L5 + L4 | 🟡 L5's half proven live: `run_tests()` (the "run AND verified" function) genuinely executes `pytest -q test_code.py` inside a real gVisor container and reports pass/fail correctly — see Session 4. L4's `node_verify` for CODING now calls `run_tests()` directly (not `run_python()`), and the write-code/write-tests/execute-code steps were each verified live in isolation this session — the one missing piece is a recorded full `--demo coding` run showing the whole loop fire end to end (deferred, see Session 8). |
| R15 | DEMO multimodal | L3 + L4 | 🟡 L3's half proven live (see R8 row) — a scanned document and a drawing image both went through real OCR extraction with correct tag recovery. L4 still needs to build the doc-QA flow that reasons over the resulting spans. |
| R16 | DEMO zero external calls | L8 | ✅ proven live, end to end: `--demo doc_qa` really runs, a real receipt writes to disk and verifies ✅ SOVEREIGN via the standalone `verify_receipt.py` (zero project imports); a real Tetragon container (colima) genuinely observed a container's `tcp_connect` and genuinely SIGKILL'd one under the enforcement policy, with the full kprobe→Sigkill→process_exit event chain captured in the log. One continuous single run of `negative_control.sh` remains outstanding due to this dev machine's memory limits, not a code gap — every mechanism it exercises is independently verified. See Session 9 (continued). |

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
- **Ollama local profile model-swap cost (measured for real on this 8 GB M1, PATCH 04,
  2026-08-25) — Session 8's bounded iteration loop must budget against this:** the local profile
  runs **sequential-with-reload**, not co-resident (see PATCH 04 for why). Ten alternating
  forced-cold completions between `gemma4:e2b` and `qwen2.5-coder:1.5b`:
  - `gemma4:e2b` reload: **TTFT median 9.3 s** (range 8.8–10.7 s), **total median 11.5 s**.
  - `qwen2.5-coder:1.5b` reload: **TTFT median 2.0 s** (range 1.7–2.0 s), **total median 2.05 s**.
  - Combined across all 10 alternating calls: **TTFT median 5.4 s, p90 10.7 s; total median
    6.5 s, p90 12.9 s.**
  - Any agent step in L4 that switches from `gemma4-e2b` to a different model (or vice versa)
    should budget **~9–11 s** of pure model-load latency before that step's first token, on this
    profile, on this hardware class.

---

## Open questions

Anything a session wanted to do but a Drift tripwire forbade. Resolve these **between**
sessions, as a team — never inside a session.

- **URGENT — a real live network call was found and reproduced in Session 9 (L8), and
  needs a fix outside L8's file scope.** Running `pytest tests/test_ingest.py` (and, by
  extension, any full-suite `pytest` run) on this dev machine opens a genuine outbound
  HTTPS connection — confirmed via `lsof -p <pid>` showing an `ESTABLISHED` TCP socket to
  a `2600:9000:...` IPv6 address, `whois`'d to **Amazon.com, Inc. (AMZ-CF — CloudFront)**,
  the CDN HuggingFace Hub serves model files through. No `HF_HUB_OFFLINE` or
  `TRANSFORMERS_OFFLINE` environment variable is set anywhere in this repo, any script,
  or the shell environment — confirmed by grep and `env`. **Root cause confirmed, not
  guessed:** setting `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` for the same `pytest`
  invocation eliminates the connection entirely (verified via `lsof` polling across the
  whole run) and all 9 `test_ingest.py` tests still pass identically, byte-for-byte the
  same pass count as without the vars. This is almost certainly Docling's
  `DocumentConverter`/layout-model construction doing a HuggingFace Hub "check for
  updates" round-trip even though the underlying model files are already cached locally
  — a well-known `huggingface_hub` behavior that only `HF_HUB_OFFLINE=1` disables. L0's
  own `preflight.py` check #6 ("HF_HUB_OFFLINE=1 in every service env") only checks the
  **vLLM service** environment, not the environment a developer's own shell (or CI) runs
  `pytest` in — this gap is exactly why it was never caught before. **This is not L8's
  file to fix** (the call happens inside L3's `core/ingest.py`, triggered by a
  third-party library) — per CLAUDE.md's protocol, raising it here rather than patching
  `core/ingest.py`, `pytest.ini`, or adding a `conftest.py` myself. **Recommended fix**
  (for whoever picks this up, likely L3's or L0's owner): set `HF_HUB_OFFLINE=1` and
  `TRANSFORMERS_OFFLINE=1` at the top of `core/ingest.py` (or in a repo-root
  `conftest.py`/`.env` loaded before Docling ever imports) so this is impossible to
  forget, not just documented. Until fixed, **anyone running this project's test suite
  on a machine with real internet access is making a live external call every time** —
  the exact claim R1 exists to make false.
- **A second, smaller hygiene gap found while diagnosing the above:** `pytest.ini` has
  no `norecursedirs`/`testpaths` restricting collection to `tests/`. A stray
  `test_code.py` left under `data/workspaces/<task_id>/` by an earlier live L4 sandbox
  run (Session 8) was picked up by pytest's default `test_*.py` discovery and broke
  collection for the **entire** repo (`!!! Interrupted: 1 error during collection !!!`)
  until manually cleaned out (`rm -rf data/workspaces/*` — safe, `data/` is gitignored
  runtime state, not tracked). Whoever next touches `pytest.ini` (CONTRACTS-owned, out
  of L8's scope) should consider `testpaths = tests` to make this class of bug
  structurally impossible rather than a recurring manual cleanup.
- **`docs/L8_AUDIT.md`'s negative_control.sh literally invokes `python -m core.graph
  --demo doc_qa`, but `core/graph.py`'s CLI (built in Session 8, before this session
  read L8's doc) only accepts `--demo coding` and `--demo approval`.** Not fixed this
  session — `core/graph.py` is L4's file, out of L8's "Files You Own" scope. Whoever
  next owns L4 should add a `doc_qa` demo path (the doc's DOC_QA plan shape already
  exists in `core/prompts.py`'s `PLAN_PROMPT_BY_TASKTYPE`, so this is additive, not a
  redesign) so `scripts/negative_control.sh` can actually run as literally specified.
- **Decide before Session 8: replace `gemma4:e2b` as the general+vision model
  (`router_model_id` / general-vision-QA role) with `moondream`.** Measured on this same 8 GB
  M1 dev machine (PATCH 05, 2026-08-29): `moondream` has the smallest true footprint of every
  candidate tested (~1.1 GB, fully GPU-offloaded, no hidden CPU buffer), is the only candidate
  that actually stays co-resident with `qwen2.5-coder:1.5b` with zero measured swap (Ollama's
  own scheduler log says "model fits alongside existing models"), reloads cold in ~1.4 s
  (vs. `gemma4:e2b`'s ~9.3 s), and passes structured-output under the same
  `response_format` mode already active in `config.yaml`. **Caveat that must be resolved before
  adopting it:** `moondream`'s default context window is **2048 tokens**, half of every other
  enabled manifest's 4096 — Session 8 (or whoever finalizes this) must check whether any real
  request path (e.g. long OCR/document-summary prompts) needs more than 2048 tokens, since
  `core/router.py`'s capability filter will reject `moondream` outright for any such request,
  and it's unverified this session whether Ollama/llama.cpp can be told to serve it at a larger
  `num_ctx` without quality loss. See PATCH 05 below for the full comparison table and the two
  rejected candidates (`gemma3:4b`, `qwen2.5vl:3b`) and why.

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

## PATCH 01 — Audit Fixes — 2026-08-25

**Status:** complete — all nine defects from the Session 3 external audit fixed exactly as
`docs/PATCH_01_AUDIT.md` specified, in order (P0-1, P0-2, P0-3, P1-4, P1-5, P1-6, P2-7, P2-8,
P2-9). One regression test per fix (two for P0-3 and P2-8, which the audit doc didn't name a
test for but which clearly needed one — a `.gitignore`-content check and a `None`-content
check for `complete_structured()` respectively). No refactor beyond the nine items; no L3–L8
files touched; `core/schemas.py` changes are additive only (two new `TaskAffinity` members, one
new validator — nothing renamed or removed).

**Files created/changed:** `core/config.py` (P0-1, P0-2), `.gitignore` (P0-3), `core/schemas.py`
(P1-4 enum additions, P2-9 validator), `core/router.py` (P1-4 filter rewrite, P1-5 fallback),
`manifests/paddleocr-vl.yaml` (P1-4), `core/serving.py` (P1-6, P2-8), `pytest.ini` (P2-7),
`tests/test_schemas.py`, `tests/test_router.py`, `tests/test_serving.py` (regression tests for
all nine).

**Fix-by-fix:**
- **P0-1** `load_settings()` no longer resolves against CWD — `_REPO_ROOT` anchors both the
  default config path and every path inside it. Test: `test_load_settings_works_from_any_cwd`.
- **P0-2** `load_settings()` now `mkdir(parents=True, exist_ok=True)`s every path in
  `settings.paths` before returning. Test: `test_load_settings_creates_directories`.
- **P0-3** `.gitignore` no longer drops `policies/*`; added `*.pem` / `data/signing_key.pem`
  ahead of Session 9. Test: `test_gitignore_does_not_drop_policies`.
- **P1-4** `TaskAffinity` gained `EMBEDDING` and `OCR_EXTRACTION` (additive). `core/router.py`'s
  affinity filter now rejects any manifest whose affinities are *entirely* internal
  (`INTERNAL_ONLY_AFFINITIES` = routing/embedding/ocr_extraction) instead of checking a single
  `excluded_affinity` field. `paddleocr-vl.yaml` now declares `task_affinities: [ocr_extraction]`
  so it is unconditionally excluded from general vision routing — confirmed live by the DoD's
  final command (see below). `RouteRequest.excluded_affinity` kept in the contract (unused by
  the filter now, per the patch's instruction not to remove it). Test:
  `test_ocr_model_excluded_from_general_vision_routing`.
- **P1-5** `_arch_router_select()` now catches `WorkbenchError` from `complete_structured()` and
  falls back to `candidates[0]` with a human-readable reason instead of propagating and killing
  the task. Test: `test_router_failure_falls_back_to_first_candidate`. **This fix changed the
  live behavior of `tests/test_router.py::test_four_demo_routes`** (integration-only, see DoD
  output below) — it no longer raises on a dead Arch-Router, it falls back, so the demo-route
  assertions now fail on model choice instead of erroring on connection. That is correct new
  behavior per the fix, not a regression; the test still needs a live Arch-Router to actually
  pass, same platform gap as every prior session.
- **P1-6** `ModelRegistry.get()` now takes `include_disabled: bool = False` and raises
  `WorkbenchError` for a disabled manifest unless the caller opts in explicitly.
  `manifest_hashes()` still returns all manifests (receipts should record what's on disk).
  `reload()` logs an error on an empty manifest set. Test: `test_get_disabled_model_raises`.
- **P2-7** `pytest.ini` registers the `integration` marker and adds
  `addopts = -m "not integration"`, so bare `pytest` is green and fast by default and
  `pytest -m integration` opts in explicitly.
- **P2-8** `complete()` and `complete_structured()` (both call sites: first attempt and the
  one-shot retry) now raise `WorkbenchError` instead of returning/validating `None`. Tests:
  `test_complete_raises_on_empty_content`, `test_complete_structured_raises_on_empty_content`.
- **P2-9** `EvidenceSpan.bbox` now has the `field_validator` the doc said was intended and
  dropped — rejects unnormalised and inverted boxes. Tests:
  `test_evidence_span_rejects_unnormalised_bbox`, `test_evidence_span_rejects_inverted_bbox`.

**Definition of Done — all four commands run for real, output pasted verbatim:**

`pytest -q` →
```
27 passed, 3 deselected in 0.26s
```

`pytest -q -m integration` → **collects, fails only on live services (expected on this
dev machine — no GPU, no vLLM, same platform gap as every prior session)**:
```
FAILED tests/test_router.py::test_four_demo_routes - AssertionError: assert 'qwen25-coder-7b' == 'qwen25-vl-7b'
FAILED tests/test_serving.py::test_health_all_green - AssertionError: not all models healthy: {...all False...}
FAILED tests/test_serving.py::test_complete_structured_returns_valid_model - core.schemas.WorkbenchError: connection to model server failed after 3 attempts: Connection error.
3 failed, 27 deselected in 18.05s
```
The `test_four_demo_routes` failure log line is itself a live proof P1-5 works:
`WARNING core.router:router.py:135 router unavailable (connection to model server failed
after 3 attempts: Connection error.); defaulting to first candidate` — no crash, a clean
fallback.

`cd /tmp && PYTHONPATH=<repo> python -c "from core.config import SETTINGS; print(SETTINGS.paths.data)"` →
```
/Users/mudabbir/Desktop/sovereign-workbench/data
```

`python -c "..."` (capability_filter image request) →
```
survivors: ['qwen25-vl-7b']
rejected: {'arch-router-1.5b': 'does not support required modality: image', 'paddleocr-vl': 'reserved for internal use (ocr extraction only) and not available for general routing', 'qwen25-coder-7b': 'does not support required modality: image'}
```
Matches the doc's requirement exactly: survivors `['qwen25-vl-7b']` only, `paddleocr-vl` in
`rejected`.

**Surprises a fresh session must know:**
- `test_filter_excludes_router_and_ocr_from_general_routing` (Session 3's test, untouched) still
  passes unmodified after the P1-4 rewrite even though it exercises the now-inert
  `excluded_affinity=TaskAffinity.VISION_EXTRACTION` path — it passes for a different reason now
  (paddleocr is unconditionally internal-only via its manifest, not because of the request field).
  Left as-is per "do not refactor beyond these nine items."
- Multiple `-m` flags on one `pytest` invocation don't merge (pytest's `-m` is a plain
  string-store option) — the CLI's `-m integration` simply overrides `pytest.ini`'s
  `-m "not integration"` addopt, which is exactly why `pytest -q -m integration` in the DoD
  works as a real opt-in rather than a no-op.
- `core/config.py` now imports `WorkbenchError` from `core/schemas.py`. Confirmed no cycle:
  `core/schemas.py` imports nothing from `core/config.py`.

**Deviations from the doc (and why):**
- Wrote two regression tests the doc didn't explicitly name (P0-3's `.gitignore` content check,
  P2-8's second guard on the retry path) — the mission brief said a fix without a test will
  regress, and both fixes are trivially regressable without one.

### Open questions
- _(none — the live-model-server gap remains the same pre-existing dev-machine/venue-machine
  environment fact from every prior session, not introduced by this patch)_

### Next action
PATCH 02 — local model profile (Gemma 4 / Ollama)

## PATCH 02 — Local Model Profile (Gemma 4 + Ollama) — 2026-08-25

**Status:** complete — built exactly to the doc's file scope (manifests, `config.yaml`, two
additive `Settings` fields + `AuditCfg`, one function in `core/serving.py`,
`scripts/probe_structured.py`, `tests/test_serving.py`). `core/router.py` untouched. This
session ran on the actual target hardware for this profile (Apple M1, 8 GB RAM — confirmed via
`system_profiler`/`sysctl`), so — unlike every prior session — the live DoD commands could
actually be run against real, locally-served models instead of failing on a platform gap.
Installed Ollama via Homebrew (`brew install ollama`) and pulled all three models for real.

**Files created/changed:** `core/config.py` (`AuditCfg`, `serving_backend`,
`structured_output_mode`, additive), `core/serving.py` (`_structured_kwargs()`, wired into
`complete_structured()`), `manifests/gemma4-e2b.yaml`, `manifests/qwen25-coder-1.5b.yaml`,
`manifests/gemma4-e2b-ocr.yaml`, `manifests/embeddinggemma-300m.yaml` (all new), the four vLLM
manifests (`qwen25-vl-7b`, `qwen25-coder-7b`, `arch-router-1.5b`, `paddleocr-vl`) set to
`enabled: false` — not deleted, per the doc, `config.yaml` (local profile values),
`scripts/probe_structured.py` (new), `tests/test_serving.py` (model-id fixtures updated to the
new manifest set + 3 new `_structured_kwargs` backend tests).

**Definition of Done — every command run for real:**

`ollama pull gemma4:e2b && ollama pull qwen2.5-coder:1.5b && ollama pull embeddinggemma` →
**all three succeeded.** `gemma4:e2b` downloaded as **7.2 GB** on disk — far larger than the
doc's ~1.5 GB estimate. This is not a bug: resident RAM while loaded (`ollama ps`) is **1.7 GB**,
matching the doc closely. The gap is Gemma's per-layer-embedding-caching architecture (the same
mechanism behind Google's real "Gemma 3n E2B/E4B" releases) — a much larger on-disk parameter
table than what's active per token. **Record this precisely: on-disk size and resident RAM are
not the same number for this model family; only the latter matters for the "fits in 8 GB" claim,
and that one checks out.**

`python scripts/probe_structured.py` →
```
Probing structured-output modes against http://127.0.0.1:11434/v1 (model=gemma4:e2b)
----------------------------------------------------------------------
[FAIL] guided_json      invalid json for schema: '```json\n{\n  "answer": "yes",\n  "confidence' (Invalid JSON: expected value at line 1 column 1)
[PASS] response_format  ok
[FAIL] ollama_format    invalid json for schema: '```json\n{\n  "answer": "yes",\n  "confidence' (Invalid JSON: expected value at line 1 column 1)
----------------------------------------------------------------------
Recommended config.yaml value: structured_output_mode: response_format
```
**Root cause of the two failures:** this Ollama build (v0.32.15) ignores `guided_json` and the
bare `format` extra_body key for this model/template combo and lets Gemma wrap its JSON in a
markdown code fence, which breaks strict parsing. Only `response_format` with
`json_schema`/`strict: true` actually constrains the output. `config.yaml` updated to
`structured_output_mode: response_format` (was `guided_json`, the vLLM-only default) — this is
exactly the "do not guess" instruction paying off; the wrong default would have silently produced
unparsable output at every structured call site.

`pytest -q` → **8 failed, 22 passed, 3 deselected** (not the clean pass the top-level DoD implies
— see Surprises below for why every one of the 8 is expected fallout, not a bug):
```
FAILED tests/test_router.py::test_filter_removes_text_only_model_for_image_request
FAILED tests/test_router.py::test_filter_removes_short_context_model
FAILED tests/test_router.py::test_filter_removes_non_grammar_model_when_structured_required
FAILED tests/test_router.py::test_filter_excludes_router_and_ocr_from_general_routing
FAILED tests/test_router.py::test_zero_survivors_raises_with_table
FAILED tests/test_router.py::test_single_survivor_skips_llm_call
FAILED tests/test_router.py::test_ocr_model_excluded_from_general_vision_routing
FAILED tests/test_schemas.py::test_load_settings_parses_config_yaml
8 failed, 22 passed, 3 deselected in 0.44s
```
`pytest tests/test_serving.py -v` (this session's own file — the doc's real scope) → **13/13
pass**, including, for the first time in this project's history, **both `@pytest.mark.integration`
tests passing for real** against a live model server (`test_health_all_green`,
`test_complete_structured_returns_valid_model`).

`python -c "..."` (health + registry, exact DoD snippet) →
```
['embeddinggemma-300m', 'gemma4-e2b-ocr', 'gemma4-e2b', 'qwen25-coder-1.5b']
{'embeddinggemma-300m': True, 'gemma4-e2b-ocr': True, 'gemma4-e2b': True, 'qwen25-coder-1.5b': True}
```
All four `True` — required one bug fix (see Surprises).

`python -c "..."` (router demo, exact DoD snippet) →
```
qwen25-coder-1.5b | This model is specialized for generating code, scripts, and engineering calculations.
gemma4-e2b | This model is specifically designed for summarising inspection reports and answering questions about documents.
gemma4-e2b | only capable model
```
Matches the doc's expected sequence exactly (`qwen25-coder-1.5b`, `gemma4-e2b`, `gemma4-e2b`).
The first two routes are **genuine live Arch-Router calls answered by `gemma4-e2b`** (not
single-survivor short-circuits) — this is R3 and R12 proven end-to-end against a real model for
the first time in this project.

**Measured tokens/sec (both chat models, `ollama run --verbose`, real generations):**
- `gemma4:e2b`: prompt eval **46.05 tok/s**, eval (generation) **31.39 tok/s** (568 tokens /
  18.10s). Well above the doc's ~8 tok/s pain threshold.
- `qwen2.5-coder:1.5b`: prompt eval **265.75 tok/s**, eval (generation) **49.36 tok/s** (346
  tokens / 7.01s).
- Resident RAM while loaded: `gemma4:e2b` **1.7 GB**, `qwen2.5-coder:1.5b` **1.2 GB** (both
  `100% GPU` per `ollama ps`, i.e. Metal, not CPU fallback).
- `embeddinggemma` embedding dimension confirmed **768** via a real `/api/embed` call (matches
  the doc's L6 dimension note — Session 6 should size the Qdrant collection at 768, not 1024).

**Surprises a fresh session must know:**
- **Bug found and fixed:** `manifests/embeddinggemma-300m.yaml`'s `served_model_name` was
  `embeddinggemma` (bare, as the doc's table names the tag), but Ollama's OpenAI-compat
  `/v1/models` reports it as `embeddinggemma:latest` (Ollama auto-appends `:latest` when a tag
  has no explicit suffix — `gemma4:e2b` and `qwen2.5-coder:1.5b` already have explicit tags and
  were unaffected). `health()` reported this model `False` until the manifest was corrected to
  `embeddinggemma:latest`. **Any new Ollama manifest for an untagged model needs the same fix.**
- **`gemma4:e2b` has a "thinking" preamble by default** (visible as literal `Thinking...`
  reasoning tokens before the answer in `ollama run`). This silently eats the `max_tokens`
  budget: a call with `max_tokens=10` or even `max_tokens=100` for a short prompt returned an
  **empty string, not an error** (`complete()`'s empty-content guard only fires on `None`, and
  Ollama returns `""` here, not `None`). Confirmed content only reliably appears with a generous
  budget (worked at `max_tokens=200`). **L4 must budget `max_tokens` generously for any
  `gemma4-e2b` call, or add an explicit check for empty (not just `None`) content** — this is a
  real, silent failure mode the P2-8 guard in `core/serving.py` does not catch, flagged here
  rather than fixed, since `complete()`'s contract (raise on `None` only) is L1's frozen behavior
  and changing it is outside this patch's file scope.
- **Co-residency of multiple models is NOT demonstrated, and empirically does not happen by
  default.** Ran `gemma4-e2b` and `qwen25-coder-1.5b` concurrently via `asyncio.gather` and
  checked `ollama ps` immediately after: only the most-recently-used model was listed. Restarted
  the Ollama server with `OLLAMA_MAX_LOADED_MODELS=4 OLLAMA_KEEP_ALIVE=30m` and repeated the test
  twice (concurrent call, then a lone follow-up call to the other model) — **both times, loading
  the second model evicted the first from `ollama ps`**, despite the keep-alive window not having
  expired and despite `MAX_LOADED_MODELS` allowing 4. Root-cause guess (not confirmed further —
  didn't want to sink this session into an Ollama internals rabbit hole): vLLM's four manifests
  are four genuinely separate processes on four separate ports, so "all resident" is structural;
  Ollama is one daemon juggling models in one process, and on this build/hardware it appears to
  serialize rather than truly co-host heterogeneous models even when told it has room to. Model
  reload is fast (a few seconds), so a demo that calls models sequentially will look fine, but
  **this profile does not currently satisfy R2's "served at once" as literally as the vLLM
  profile does.** Recorded as an open question below rather than chased further or "fixed" by
  touching `core/router.py`/L0's service-start scripts, both out of this session's file scope.
- Had to `brew install ollama` (not previously installed) and start the server manually
  (`ollama serve` via `nohup`, not `brew services start ollama` — this session's shell only,
  not a persistent launchd service). A future session or the real venue setup should decide
  whether Ollama should be a `brew services`-managed daemon and should set
  `OLLAMA_MAX_LOADED_MODELS`/`OLLAMA_KEEP_ALIVE` explicitly rather than relying on defaults, given
  the co-residency finding above.
- `pytest -q`'s 8 failures are **all** pre-existing tests outside this session's file scope
  (`tests/test_router.py` ×7, `tests/test_schemas.py` ×1) that hardcode the vLLM demo-box
  manifest ids (`qwen25-vl-7b`, etc.) and read the live `REGISTRY`/`SETTINGS` singletons rather
  than an isolated fixture (unlike `test_new_manifest_is_routable_without_code_change`, which
  already does this correctly via `monkeypatch.setattr(router, "REGISTRY", ...)`). Swapping the
  active manifest set is the entire point of this patch (R4), so these tests failing is the
  literal, correct, and doc-anticipated consequence — not a defect in the files this session
  owns. Per `CLAUDE.md`'s "do not rewrite another layer's files" rule, `tests/test_router.py` was
  left untouched; see Open questions for the fix a future L2 session should make.
- `tests/test_schemas.py::test_load_settings_parses_config_yaml` fails for the same reason on
  two assertions this patch's mandated `config.yaml` changes directly contradict:
  `sandbox.runtime == "runsc"` (patch requires `runc` on macOS) and (implicitly, via the same
  test) the old `router_model_id` default. Also left untouched — owned by the CONTRACTS session.
- Needle 2 probe: **not run, no-go this session.** `scripts/probe_needle.py` per the doc needs
  "two real tool schemas from `TOOL_REGISTRY`" — `TOOL_REGISTRY` doesn't exist yet (`core/tools.py`
  is L5, not built until the next session). Writing a probe against a registry that doesn't exist
  would be exactly the kind of half-finished stub `CLAUDE.md` forbids. Per the doc's own framing
  ("do not adopt Needle without running the probe"), the correct call with zero data is: **do not
  adopt.** `cactus-needle` was not added to `requirements.txt`. Whoever builds L5 should run this
  probe once `TOOL_REGISTRY` exists, before deciding on Needle.

**Deviations from the doc (and why):**
- `manifests/embeddinggemma-300m.yaml`'s `served_model_name` is `embeddinggemma:latest`, not the
  bare `embeddinggemma` the doc's model-stack table names — required correction, see Surprises.
- Everything else matches the doc's file shape and content exactly, including keeping the four
  vLLM manifests on disk with `enabled: false` rather than deleting them.

### Open questions
- ~~R2 co-residency gap on the Ollama profile~~ — **resolved empirically, see PATCH 04.** Root
  cause found (memory-pressure-aware scheduler + `gemma4:e2b`'s true ~6.5 GB footprint, not the
  1.7 GB this session assumed), reload cost measured, decision made: sequential-with-reload, not
  co-resident.
- Whether `tests/test_router.py`'s stage-1 filter tests should be rewritten to build an isolated
  `ModelRegistry` fixture (like `test_new_manifest_is_routable_without_code_change` already does)
  instead of depending on the live enabled-manifest set on disk, so a future manifest-profile swap
  doesn't break 7 tests again. This is an L2-session call, not made here. (Resolved in PATCH 03,
  see below, before this note was even acted on.)

### Next action
Session 4 — L5 Tool & Sandbox Plane — start with `sandbox/Dockerfile`.

## PATCH 03 — Profile-Agnostic Tests — 2026-08-25

**Status:** complete. Root cause of PATCH 02's 8 test failures was a genuine test defect, not a
code defect, exactly as diagnosed: `tests/test_router.py` (7 tests) and
`tests/test_schemas.py` (1 test) hardcoded vLLM-profile manifest ids/config values instead of
treating the active profile as data — which is R4's entire point. Fixed in `tests/` only.
`core/router.py`, every manifest, and `config.yaml` are untouched (only their `enabled` flags
were flipped twice, temporarily, to prove the fix, then restored to the original Ollama-active
state).

**Files created/changed:** `tests/test_router.py` (full rewrite — isolated fixture-manifest
builder + `monkeypatch.setattr(router, "REGISTRY", ...)` for every unit test;
`_unique_model_with_affinities()` helper derives expected model ids from the live registry's
`task_affinities` for the integration demo-route test), `tests/test_schemas.py`
(`test_load_settings_parses_config_yaml` now asserts structure/types, not literal profile
strings), `tests/test_serving.py` (found and fixed the **same** latent defect in a test this
session did not originally ask about — see Surprises: `test_registry_loads_four_manifests` and
three others hardcoded Ollama-profile ids).

**Definition of Done:**

`pytest -q` with the **Ollama profile active** (repo's tracked state:
`gemma4-e2b`/`qwen25-coder-1.5b`/`gemma4-e2b-ocr`/`embeddinggemma-300m` enabled, four vLLM
manifests disabled) →
```
30 passed, 3 deselected in 0.43s
```

Then flipped **every** manifest's `enabled` flag (vLLM: false→true, Ollama: true→false) and
reran with no other changes:
```
1 failed, 29 passed, 3 deselected in 0.40s
FAILED tests/test_serving.py::test_registry_loads_four_manifests - AssertionError: assert {'arch-router...qwen25-vl-7b'} == {'embeddingge...5-coder-1.5b'}
```
This is the **same bug class** in a file this session wasn't originally asked to touch — a test
this project's own PATCH 02 session wrote a few hours earlier, hardcoding the very ids it was
demonstrating. Fixed it (see Surprises) and reran with the vLLM profile still active:
```
30 passed, 3 deselected in 0.42s
```
Flipped back to the **Ollama profile** (restoring the exact enabled/disabled state this repo
had before this session started) and ran a third time:
```
30 passed, 3 deselected in 0.39s
```
All three runs: 30 passed, 3 deselected, 0 failed. `pytest -q -m integration` also reran clean
against live Ollama after all the edits: `3 passed, 30 deselected in 49.65s` (health, structured
completion, and the router's four-demo-route test — the last one now resolves its expected
model ids from `REGISTRY.all()`'s `task_affinities` instead of a hardcoded name, so it is the
one test in the suite that is simultaneously live *and* profile-agnostic).

**Surprises a fresh session must know:**
- **The DoD's "flip and prove both directions" step caught a real bug the original ask didn't
  know about.** `tests/test_serving.py::test_registry_loads_four_manifests` (written in the
  PATCH 02 session, a few hours before this one) asserted the literal Ollama-profile id set —
  identical mistake, different file. It is now a structural check: it reads every manifest
  file's own `enabled:` flag off disk and asserts `REGISTRY.all()` matches that set exactly,
  plus `len == 4` (a real invariant both profiles share). This is the correct lesson of this
  patch: "fix the two files the report named" would have left the suite fully green under the
  *original* profile but silently broken the moment someone flipped it back — precisely the
  failure mode this task exists to close out. Three other `test_serving.py` tests
  (`test_complete_rejects_images_for_text_only_model`,
  `test_complete_raises_on_empty_content`, `test_complete_structured_raises_on_empty_content`,
  plus the integration test `test_complete_structured_returns_valid_model`) hardcoded
  `"qwen25-coder-1.5b"` / `"gemma4-e2b"` too. These didn't *fail* `pytest -q` under either
  profile (disabling a hardcoded id makes `REGISTRY.get()` raise `WorkbenchError` for "disabled"
  instead of for the behavior actually under test — a false pass, not a crash), but were fixed
  anyway via `_enabled_text_only_model_id()` / `_any_enabled_model_id()` /
  `_enabled_grammar_model_id()` helpers that query the live registry, because a test passing for
  the wrong reason is exactly the defect this patch is about, even when `pytest -q`'s exit code
  doesn't reveal it.
- **`core/router.py`'s `capability_filter()` reads the module-level `REGISTRY` name from
  `core.serving` by reference, not a value captured at import time** (a design already noted by
  Session 3) — this is what makes `monkeypatch.setattr(router, "REGISTRY", fixture_registry)`
  work for every unit test in `tests/test_router.py` now, not just the one R4 test that already
  used this pattern before this session.
- The now-inert `RouteRequest.excluded_affinity` field (dead since PATCH 01's P1-4 rewrite —
  `capability_filter`'s affinity check now unconditionally excludes any manifest whose
  affinities are *entirely* internal, regardless of what the request passes) meant
  `test_filter_excludes_router_and_ocr_from_general_routing`'s old two-case shape (default vs.
  explicit `excluded_affinity=VISION_EXTRACTION`) was testing a distinction that no longer
  exists. Simplified to directly assert both a routing-only and an ocr-only fixture manifest are
  excluded from an ordinary request, with a docstring explaining why, instead of preserving a
  test shape whose premise PATCH 01 already removed.
- `test_new_manifest_is_routable_without_code_change` previously proved R4 by copying the repo's
  *real* manifest files into `tmp_path` and adding a fifth. That still passed under either
  profile (it only counts, never asserts specific ids), but per the letter of this session's
  instruction ("must never depend on the repo's active manifests/ contents"), it now writes the
  same synthetic 4-manifest fixture set used everywhere else in the file, plus the fifth. Same
  proof, zero dependency on disk state.
- The `@pytest.mark.integration` demo-route test is the one place a hardcoded id would have been
  defensible (it needs a live Arch-Router-equivalent to actually reason about task fit, so it
  can't be run against a synthetic fixture the way the unit tests are) — instead it derives
  `general_model`/`coding_model` from the real, active `REGISTRY`'s `task_affinities` via
  `_unique_model_with_affinities()`, which asserts exactly one match and fails loudly (not
  silently) if a future profile's shape stops being 1:1 on those affinities.

**Deviations from the doc (and why):** none — `docs/L2_ROUTER.md`'s required API
(`capability_filter`, `route`, `RouteRequest`, etc.) and `docs/01_CONTRACTS.md`'s frozen types
are unchanged; this was a `tests/`-only fix as instructed.

### Open questions
- _(none new — this patch closed the two open questions PATCH 02 raised about
  `tests/test_router.py`'s profile-coupling. The R2 co-residency gap PATCH 02 flagged is
  unrelated to this patch and was still open at the time this patch ended — resolved
  afterward, see PATCH 04.)_

### Next action
Session 4 — L5 Tool & Sandbox Plane

## PATCH 04 — Co-Residency Investigation — 2026-08-25

**Status:** complete. Investigation only, as instructed — no application code, manifests, or
`config.yaml` changed. Resolves the open question PATCH 02 raised: models were not co-resident
by default even with `OLLAMA_MAX_LOADED_MODELS=4`. Root cause found empirically, is not what the
hypothesis suggested, and reveals a real correction to PATCH 02's own numbers.

**Configuration this project runs under, stated plainly: sequential-with-reload, not
co-resident.** Co-residency is technically achievable on this hardware (observed directly, see
Step 3) but happens only when transient system memory allows it, and — per the decision rule
this task set in advance — causes heavy swapping when it does happen. **Recommendation:
sequential loading, accept the reload cost.** `OLLAMA_MAX_LOADED_MODELS=4` /
`OLLAMA_KEEP_ALIVE=24h` are left configured (harmless — they let same-model-repeated steps stay
warm, and let Ollama opportunistically co-load when memory genuinely allows it) but nothing in
this project should assume or design around co-residency actually holding.

**Step 1 — baseline (no special config, plain `ollama serve`):** loaded `gemma4:e2b` → `ollama
ps` showed **1 row** (1.7 GB, 100% GPU). Loaded `qwen2.5-coder:1.5b` next → `ollama ps` showed
**1 row** again (`qwen2.5-coder:1.5b` only — `gemma4:e2b` was evicted). Confirms PATCH 02's
original observation, freshly reproduced.

**Step 2 — testing the hypothesis (env var set in a client shell, server on launchd never saw
it):** There is no Ollama.app on this machine (Homebrew CLI only, confirmed —
`/Applications` has no Ollama entry). `launchctl setenv OLLAMA_MAX_LOADED_MODELS 4` and
`launchctl setenv OLLAMA_KEEP_ALIVE 24h`, then restarted the server as a real launchd-managed
process via `brew services start ollama` (the closest equivalent to "relaunch the app" available
here). Confirmed, two independent ways, that the running server process actually received both
variables:
```
$ launchctl print gui/$(id -u)/homebrew.mxcl.ollama | grep -A3 "inherited environment"
	inherited environment = {
		OLLAMA_KEEP_ALIVE => 24h
		OLLAMA_MAX_LOADED_MODELS => 4
		...
$ ps eww <pid> | tr ' ' '\n' | grep OLLAMA
OLLAMA_KEEP_ALIVE=24h
OLLAMA_MAX_LOADED_MODELS=4
```
**The hypothesis is disproven.** In PATCH 02 the variables were already being passed directly to
the `ollama serve` process in the same shell command that launched it (not a separate export, so
launchd-vs-shell scoping was never actually the mechanism at play) — and here, with the variables
confirmed reaching the process through the launchd path the hypothesis named, **the very next
co-load attempt still evicted the first model**:
```
time=...22:32:49... msg="llama-server model predicted to exceed available memory, evicting" predicted="1.0 GiB" available="1.1 GiB" gpu_free="3.8 GiB" system_free="1.1 GiB" system_limited=true
```

**Step 3 — repeated the load test.** Immediately after the disproof above: still **1 row**
(gemma evicted). But re-running the same alternating-load pattern a few minutes later (as part of
Step 4's measurement), `ollama ps` showed **2 rows simultaneously**:
```
NAME                  ID              SIZE      PROCESSOR    CONTEXT    UNTIL
gemma4:e2b            7fbdbf8f5e45    1.7 GB    100% GPU     4096       24 hours from now
qwen2.5-coder:1.5b    d7372fd82851    1.1 GB    100% GPU     4096       24 hours from now
```
**Real root cause (from the server's own log, not a guess):** Ollama's scheduler is
memory-pressure-aware. It logs its exact reasoning every time it evicts:
`"llama-server model predicted to exceed available memory, evicting" ... system_limited=true`.
`OLLAMA_MAX_LOADED_MODELS` sets a ceiling on *how many* models are allowed to be considered for
residency — it does not override the scheduler's live check of actual free system memory before
allowing a second model to load. Whether co-residency happens is a function of how much RAM is
genuinely free on this machine at that moment (which fluctuates with whatever else is running —
Claude Code, Terminal, Safari/WebKit, windowserver — all visible competing for RAM in `ps aux`
during this session), not something `OLLAMA_MAX_LOADED_MODELS` can force.

**A second, more important correction this investigation surfaced:** PATCH 02 reported
`gemma4:e2b`'s resident RAM as **1.7 GB**, reading only `ollama ps`'s "SIZE" column (GPU-resident
only). The server log shows `gemma4:e2b` *also* allocates a dedicated **CPU-side buffer of
4795 MiB (~4.8 GB)** on every load (`load_tensors: CPU model buffer size = 4795.00 MiB`),
consistent across every single load in the log, on top of the ~1.7 GB GPU (Metal) buffer. **True
total footprint while `gemma4:e2b` is loaded is ~6.5 GB, not 1.7 GB.** This lines up with the
scheduler's own "predicted='6.8 GiB'" eviction-reasoning line seen for gemma reloads, and it
explains why free memory disappears so fast on an 8 GB machine the moment `gemma4:e2b` loads.
`qwen2.5-coder:1.5b` loads via `mmap` (page-cache-backed, no equivalent dedicated buffer logged)
and has a much lighter true footprint, matching its originally-reported ~1.1–1.2 GB. **PATCH 02's
"1.7 GB, matches the doc's ~1.5 GB estimate, the effective-2B trick checks out" conclusion was
incomplete — it is now superseded by this ~6.5 GB true-footprint finding.**

**Step 4 — swap cost, measured for real** (`urllib`-based streaming client against the raw
`/v1/chat/completions` endpoint, timing time-to-first-streamed-chunk vs. total, 10 alternating
calls between `gemma4:e2b` and `qwen2.5-coder:1.5b`, `ollama stop` on both models issued before
every single call to force a genuine cold reload each time — `keep_alive: 0` in the request body
was tried first and did **not** reliably force eviction on this build, a useful negative result
recorded here so nobody relies on it):
```
call  1  model=gemma4:e2b            ttft= 10173.6 ms  total= 12370.5 ms
call  2  model=qwen2.5-coder:1.5b    ttft=  1980.0 ms  total=  2029.8 ms
call  3  model=gemma4:e2b            ttft=  9321.6 ms  total= 11458.6 ms
call  4  model=qwen2.5-coder:1.5b    ttft=  2000.2 ms  total=  2052.0 ms
call  5  model=gemma4:e2b            ttft= 10743.5 ms  total= 12911.0 ms
call  6  model=qwen2.5-coder:1.5b    ttft=  1690.3 ms  total=  1737.7 ms
call  7  model=gemma4:e2b            ttft=  8835.2 ms  total= 10984.3 ms
call  8  model=qwen2.5-coder:1.5b    ttft=  2015.4 ms  total=  2065.4 ms
call  9  model=gemma4:e2b            ttft=  9080.9 ms  total= 11231.9 ms
call 10  model=qwen2.5-coder:1.5b    ttft=  2020.0 ms  total=  2068.9 ms

TTFT   median=  5427.6 ms   p90= 10686.5 ms   (all 10 calls, mixed models)
TOTAL  median=  6526.6 ms   p90= 12856.9 ms

gemma4:e2b            TTFT median  9321.6 ms   TOTAL median 11458.6 ms
qwen2.5-coder:1.5b    TTFT median  2000.2 ms   TOTAL median  2052.0 ms
```
This is now recorded under `## Environment facts` for Session 8 to read directly.

**Step 5 — memory pressure during Step 4:** real, reproducible, heavy swapping, confirmed twice
independently.
```
Before the mixed (accidentally-co-resident) run: vm.swapusage used=1189.62M free=858.38M
After that run:                                  vm.swapusage used=5613.38M free=530.62M  (swap FILE itself grew 2048M → 6144M)
Pages free crashed from 25042 (~410 MB) to 3981 (~65 MB)

Before the forced-cold Step 4 run: Swapouts=3,373,070 (cumulative page counter)
After it:                          Swapouts=4,574,529   → +1,201,459 pages ≈ 19.7 GB of new pageout activity in ~2 minutes
```
**Yes, the machine swaps — heavily — every time `gemma4:e2b` loads its ~6.5 GB true footprint
alongside macOS and this session's own tooling (Claude Code, Terminal, browser).** Per the
decision rule set for this investigation: co-residency being technically achievable does not
mean it should be used. **Sequential loading is the correct, accepted answer for this profile on
this hardware class**, exactly as Step 5 anticipated.

**Nothing built:** no scheduler, no keep-alive manager, no model-swap logic. `OLLAMA_MAX_LOADED_MODELS`/`OLLAMA_KEEP_ALIVE` were set via `launchctl setenv` (host/service configuration, not
application code) and the server was switched from an ad-hoc `nohup ollama serve &` to a real
`brew services start ollama` (launchd-managed) process — left running this way since it is a
more correct, standard way to run this server long-term and does not conflict with the
sequential-with-reload conclusion.

**Surprises a fresh session must know:**
- `keep_alive: 0` sent in an OpenAI-compat `/v1/chat/completions` request body did **not**
  reliably force Ollama to unload the model afterward on this build — do not rely on it for
  testing or for any future "unload after use" logic. `ollama stop <model>` (CLI) is the reliable
  way to force an unload.
- The measurement script used `urllib` directly against the raw REST endpoint (not
  `core.serving.complete()`) specifically to get accurate time-to-first-streamed-token timing,
  which `core.serving.complete()` does not expose (it only returns the final assembled string,
  by design — L1's contract is a plain non-streaming `complete()`). No change was made to
  `core/serving.py` to support this; the measurement script lives outside `core/` entirely.
- `brew services start ollama` occasionally reported `Running: false, Loaded: false`
  immediately after a `pkill` + fresh start, self-resolving as a transient race on a
  second `brew services start ollama` a few seconds later — recorded in case it recurs;
  did not investigate further since a second start command reliably fixed it both times it
  happened here.

**Deviations from the doc (and why):** none — this session touched no doc-scoped file
(`core/`, `manifests/`, `config.yaml` all untouched). All changes were host/service
configuration (`launchctl setenv`, `brew services`), explicitly permitted by the "record, do not
build" framing of the task.

### Open questions
- _(none — this fully resolves the open question PATCH 02 raised)_

### Next action
Session 4 — L5 Tool & Sandbox Plane — start with `sandbox/Dockerfile`

## PATCH 05 — Vision Model Footprint Comparison — 2026-08-29

**Status:** complete. Measurement only, as instructed — no application code, manifests, or
`config.yaml` changed. Tests whether a non-PLE multimodal model beats `gemma4:e2b`'s ~6.5 GB
true footprint (PATCH 04) on this same 8 GB M1 machine. Ran on real, locally-served Ollama
models the whole session (server already running via `brew services`, same as PATCH 04 left
it — hit the same transient `brew services start` race PATCH 04 noted once, second start
command fixed it).

**Models tested:** `gemma3:4b` and `qwen2.5vl:3b` as instructed, plus `moondream` — substituted
for `qwen2.5vl:3b` mid-session at the user's request after `qwen2.5vl:3b` caused real, felt
desktop lag (see below); `qwen2.5vl:3b`'s measurement was stopped early once the cause was
already conclusively bad, per the task's own decision rule ("a model that swaps regardless of
speed is unusable").

**Method:** mirrors PATCH 04 exactly — a `urllib`-based streaming client against the raw
`/v1/chat/completions` endpoint (script lived in the session scratchpad only, not committed) for
accurate TTFT, `ollama stop` before cold-reload measurements, `ollama ps` **and** the server log
(`/opt/homebrew/var/log/ollama.log`, grepped for `buffer size` / `predicted` / `evicting` /
`fits alongside existing models`) for true resident footprint — not `ollama ps`'s SIZE column
alone, per this task's explicit instruction and PATCH 04's own corrected lesson about
`gemma4:e2b`. `sysctl vm.swapusage` and `vm_stat`'s `Swapouts` counter (not just a single
before/after snapshot — the raw page delta) for swap evidence. `scripts/probe_structured.py`'s
`_probe_one`/`_MODES` imported directly (not duplicated) to test all three structured-output
request shapes.

**Comparison table:**

| Model | True footprint | tok/s (warm / cold) | TTFT (warm / cold) | Co-resident w/ `qwen2.5-coder:1.5b` | Swap | Structured output |
|---|---|---|---|---|---|---|
| `gemma4:e2b` (baseline, not re-measured — PATCH 02/04 numbers) | **~6.5 GB** (1.7 GB GPU + 4.8 GB hidden CPU buffer) | 31.4 tok/s (warm) | — / 9.3 s median (cold reload) | No — evicts | **Yes — heavy** (PATCH 04 Step 5: +1.2M pageout pages in ~2 min) | Yes (`response_format` only) |
| `gemma3:4b` | **~3.2 GB** (2.8 GB per `ollama ps`; log sum: 525 MiB CPU + 2367.5 MiB GPU + KV/compute buffers ≈ 3.18 GB; fully offloaded 35/35 layers, no hidden CPU buffer) | 18.4 / 11.6 | 463 ms / 5.1 s | **No** — second-model load evicted; log: `predicted="3.8 GiB" ... system_limited=true ... evicting` | **Yes** — used swap +898 MB (393.6→1291.3 MB), Swapouts +57,448 pages, during the co-load attempt alone | Yes (`response_format` only — `guided_json`/`ollama_format` both wrap in a markdown fence and fail, same failure mode as `gemma4:e2b`) |
| `qwen2.5vl:3b` | **~5.5 GB**, only **18/37 layers offloaded to GPU** (24%/76% CPU/GPU split — worse than `gemma4:e2b`'s ratio problem, inverted) | not measured — a single warm 200-token call did not finish in >3 minutes | 11.0 s cold, for a **trivial 20-token** call (never got a clean 200-token number) | **Not tested — disqualified first** | **Yes — severe.** A single load+completion took swap `used` from 0 → 2.56 GB and `Swapouts` +≈1.78M pages (≈29 GB of pageout activity) in well under a minute; **caused real, user-felt system lag** — user asked to stop it mid-measurement and the process was killed | **Not tested — disqualified first** (swap alone is disqualifying per this task's decision rule) |
| `moondream` | **~1.1 GB** (log sum: 56.25 + 732.30 + KV 204 + compute buffers ≈ 1.09 GB, matches `ollama ps`'s 1.1 GB exactly — no hidden-buffer discrepancy); fully offloaded 25/25 layers | 56.6 / 42.3 | 246 ms / 1.4 s | **Yes** — both models stayed resident simultaneously (`ollama ps` showed 2 rows, 1.1 GB + 1.1 GB); server log explicitly: `"llama-server model fits alongside existing models"` | **No** — `Swapouts` counter identical before/after (3,226,048 → 3,226,048), zero new pageout activity | Yes (`response_format` only, same markdown-fence failure on the other two modes as every other model tested) |

**Recommendation: `moondream`**, on measured footprint and swap behaviour, not benchmark
scores. It is the smallest true footprint by a wide margin (~1.1 GB vs. 3.2–6.5 GB for every
other candidate), the only one that actually achieves real co-residency with the coder model
with zero measured swap, has the fastest cold-reload TTFT of any model measured in this
project so far (1.4 s vs. `gemma4:e2b`'s 9.3 s), and passes structured output under the
already-active `response_format` mode — the same fatal-if-failed gate the task named. **`gemma3:4b`
is a real improvement over `gemma4:e2b` (~3.2 GB vs. ~6.5 GB) but still swaps on co-load and is
not recommended over `moondream`. `qwen2.5vl:3b` is disqualified outright** — worse footprint
behaviour than the model this investigation was trying to replace, and the only candidate that
produced directly observable, real-time system lag during measurement.

**Open caveat carried into the Open Questions section above (not resolved this session,
per the task's explicit instruction to record it there for a Session 8 decision):**
`moondream`'s default context window is 2048 tokens vs. every other enabled manifest's 4096 —
unverified whether this can be safely raised via `num_ctx`, and unverified whether any real
request path in this project needs more than 2048 tokens of context. `core/router.py`'s
capability filter would reject `moondream` for any request that does.

**Surprises a fresh session must know:**
- **`qwen2.5vl:3b` is not simply "a slower model" — it fails to fully fit on GPU on this
  hardware at all** (18/37 layers, vs. `gemma3:4b`'s 35/35 and `moondream`'s 25/25), and the
  resulting CPU/GPU split appears to be what triggers the severe swap, not just raw model size
  (`qwen2.5vl:3b` is smaller on disk than `gemma4:e2b` yet swapped far worse, far faster, from a
  single call rather than only under repeated alternating load like PATCH 04 needed to show for
  `gemma4:e2b`).
- **`keep_alive`/env vars from PATCH 04 did not persist across the machine's restart since
  that patch** — `launchctl print` showed no `OLLAMA_MAX_LOADED_MODELS`/`OLLAMA_KEEP_ALIVE` in
  the running server's environment at the start of this session, and the ollama server itself
  was not running at all (had to `brew services start ollama`, same transient
  `Running: false, Loaded: false` race PATCH 04 flagged, same fix: run the start command again).
  Re-applied both via `launchctl setenv` + `brew services restart ollama` before measuring, to
  keep this session's methodology consistent with PATCH 04's. **Also newly observed, not set by
  this session:** `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` were already present
  in the running server's environment — persisted from some earlier, unrecorded configuration
  step outside any session's log. Left as-is (not this session's file scope), flagged here so a
  future session doesn't mistake them for this session's doing.
- The user directly observed and reported real desktop lag from `qwen2.5vl:3b` mid-measurement
  before this session's own swap numbers were even fully read back — the model/swap evidence and
  the user's lived experience agree exactly, which is a useful sanity check on the measurement
  methodology itself (the `vm_stat`/`sysctl` numbers are not just abstractly bad, they correspond
  to a machine a person is actively using becoming unusable).
- All measurement tooling (`measure_model.py`, the ad-hoc `probe_structured.py`-reuse snippets)
  lived in the session scratchpad, not the repo, per "change no application code" — nothing new
  was added to `scripts/` this session.

**Deviations from the task's instructions (and why):**
- Substituted `moondream` for `qwen2.5vl:3b` partway through, at the user's explicit request,
  after `qwen2.5vl:3b` was already conclusively disqualified on footprint/swap grounds (its
  tok/s and structured-output steps were never run — recorded as "not tested" above, not as a
  failure, since the task's own decision rule already made the outcome moot before those steps).
- No manifests/`config.yaml`/`core/` files touched, per instruction. Recommendation recorded in
  `## Open questions` above, per instruction, for a decision before Session 8.

### Open questions
- See `## Open questions` at the top of this document — the `moondream` recommendation and its
  2048-token-context caveat are recorded there, not duplicated here.

### Next action
Session 4 — L5 Tool & Sandbox Plane — start with `sandbox/Dockerfile`

## Session 4 — L5 Tool & Sandbox Plane — 2026-08-29

**Status:** complete. Built exactly to `docs/L5_SANDBOX.md`'s file scope
(`core/sandbox.py`, `core/tools.py`, `sandbox/Dockerfile`, `sandbox/requirements.txt`,
`tests/test_sandbox.py`) with the required API (`workspace_for`, `run_python`, `run_tests`,
`verify_calculation`, `TOOL_REGISTRY`, `call_tool`). Unlike every prior session, this one had a
**real, working Docker daemon with real gVisor (`runsc`)** for the entire session — every DoD
command below ran for real against real containers, not mocked or stubbed. `docker` isn't
installed as a running daemon on macOS by default (same gap Sessions 1–3 hit — `docker info`
failed with "no such file or directory" on the socket at session start), but `colima` was
already installed (Homebrew) and unused. Started a colima Linux VM
(`colima start --cpu 2 --memory 3 --disk 20`, macOS Virtualization.Framework backend, real
Ubuntu 24.04.4 LTS aarch64 kernel 6.8), which gave a genuine Docker Engine. Then, since gVisor
is Linux-only and colima's VM *is* Linux, installed real `runsc` inside that VM from Google's
official apt repo (`https://storage.googleapis.com/gvisor/releases`) and confirmed it registered
as a docker runtime (`docker info` → `Runtimes: io.containerd.runc.v2 runc runsc`). This is not
part of any owned file — it's host/VM setup, the same category of action Sessions 4(PATCH 04)/
5(PATCH 05) took for Ollama service configuration — no scripts or files were added to the repo
for it.

**Files created/changed:** `core/sandbox.py`, `core/tools.py`, `sandbox/Dockerfile`,
`sandbox/requirements.txt`, `tests/test_sandbox.py` (all new, this session's full "Files You
Own" list). Also touched, outside the owned list, both minimal and justified:
`config.yaml` (`sandbox.runtime: runc` → `runsc`, since it's now genuinely available and
verified working here — see Deviations below).

**Definition of Done — all three commands run for real, output pasted verbatim:**

`docker build -t sovereign-sandbox:latest sandbox/` →
```
Successfully built c168b7a064ac
Successfully tagged sovereign-sandbox:latest
```
Image size: **571MB** (`docker images sovereign-sandbox:latest` → `571MB`). No `requests`/
`httpx`/`urllib3` in the image — `sandbox/requirements.txt` is exactly the six pinned packages
the doc names (pandas, numpy, openpyxl, pint, sympy, pytest), nothing else.

`pytest tests/test_sandbox.py -v` →
```
collected 23 items

tests/test_sandbox.py::test_hello_world_runs PASSED                      [  4%]
tests/test_sandbox.py::test_network_is_unreachable PASSED                [  8%]
tests/test_sandbox.py::test_import_requests_fails PASSED                 [ 13%]
tests/test_sandbox.py::test_timeout_kills_container PASSED               [ 17%]
tests/test_sandbox.py::test_container_always_removed PASSED              [ 21%]
tests/test_sandbox.py::test_runtime_is_runsc_or_documented_fallback PASSED [ 26%]
tests/test_sandbox.py::test_run_tests_reports_pytest_failure PASSED      [ 30%]
tests/test_sandbox.py::test_run_tests_reports_pytest_success PASSED      [ 34%]
tests/test_sandbox.py::test_verify_calculation_agrees_on_simple_case PASSED [ 39%]
tests/test_sandbox.py::test_verify_calculation_flags_unit_mismatch PASSED [ 43%]
tests/test_sandbox.py::test_verify_calculation_raises_on_bad_expression PASSED [ 47%]
tests/test_sandbox.py::test_path_traversal_blocked PASSED                [ 52%]
tests/test_sandbox.py::test_write_outside_workspace_requires_approval PASSED [ 56%]
tests/test_sandbox.py::test_read_outside_workspace_and_uploads_is_hard_error PASSED [ 60%]
tests/test_sandbox.py::test_fs_write_then_read_round_trips_inside_workspace PASSED [ 65%]
tests/test_sandbox.py::test_sheet_write_then_read_round_trips PASSED     [ 69%]
tests/test_sandbox.py::test_tool_registry_has_exactly_seven_tools PASSED [ 73%]
tests/test_sandbox.py::test_call_tool_returns_toolcall_record PASSED     [ 78%]
tests/test_sandbox.py::test_call_tool_reraises_workbench_error_with_attached_record PASSED [ 82%]
tests/test_sandbox.py::test_call_tool_unknown_tool_raises PASSED         [ 86%]
tests/test_sandbox.py::test_kb_search_delegates_and_fails_loudly_until_l6_exists PASSED [ 91%]
tests/test_sandbox.py::test_code_exec_via_call_tool_runs_in_sandbox PASSED [ 95%]
tests/test_sandbox.py::test_code_test_via_call_tool_is_r14_run_and_verified PASSED [100%]

============================== 23 passed in 6.27s ==============================
```
The network test really did run `socket.create_connection(("1.1.1.1", 80))` inside a real
`runsc` container with `network_mode="none"` and got `BLOCKED: OSError` — confirmed twice, once
via a raw manual `docker run --runtime=runsc --network=none ...` (see Surprises) and again
through the test suite itself.

`docker ps -a | grep sovereign-sandbox` → **empty** (grep exit code 1 = no match). Full
`docker ps -a` shows only a pre-existing, unrelated `rag-postgres` container from before this
session — not touched, not ours.

Full repo suite also reran clean on top of this: `pytest -q` → **53 passed, 3 deselected**
(the 30 pre-existing + this session's 23, zero regressions).

**Runtime actually in use:** `runsc` (real gVisor), not the `runc` fallback — confirmed via
`docker info` inside the colima VM (`Runtimes: io.containerd.runc.v2 runc runsc`) and via a
manual `docker run --runtime=runsc ...` that both executed code and blocked network access for
real. `config.yaml`'s `sandbox.runtime` was flipped from `runc` to `runsc` this session — see
Deviations.

**Sandbox image size:** 571MB (`python:3.11-slim` base + pandas/numpy/openpyxl/pint/sympy/pytest).

**Observed cold-start latency:** median **~340ms** end-to-end (container create → run →
collect logs → remove), measured over 5 consecutive `run_python(tid, "print(1)")` calls: 331,
343, 328, 348, 343 ms. This is dramatically faster than any prior session's model-load latency
numbers (unrelated subsystem, but worth noting for demo pacing) — a code-exec tool call is not
the bottleneck in this system.

**Surprises a fresh session must know:**
- **`docker.from_env()` needs `DOCKER_HOST` set explicitly on this machine.** colima's Docker
  context (`unix:///Users/mudabbir/.colima/default/docker.sock`) is what the `docker` CLI uses
  automatically (it reads the active docker context), but the Python `docker` SDK's
  `from_env()` does **not** consult docker contexts — it only reads `DOCKER_HOST` (or falls
  back to `/var/run/docker.sock`, which doesn't exist here). Every real run this session needed
  `export DOCKER_HOST="unix:///Users/mudabbir/.colima/default/docker.sock"` first. **This is a
  dev-machine-only fact** — the real venue Ubuntu box will have native Docker Engine at the
  standard socket path and won't need this. Recorded here so a fresh session doesn't waste time
  rediscovering it, and so nobody "fixes" `core/sandbox.py` to hardcode a colima socket path
  (that would break the real venue deployment).
- **Bug found and fixed: `run_tests()` originally wrote the workspace module as `code.py`,
  which collides with Python's own stdlib `code` module** (the interactive-interpreter helper).
  `from code import add` in the test file silently resolved to the *stdlib* module instead of
  the workspace file (`ImportError: cannot import name 'add' from 'code'
  (/usr/local/lib/python3.11/code.py)`), making every `run_tests()` call fail regardless of
  whether the agent's code was correct. Fixed by writing the module as `solution.py` instead;
  `tests` strings must `from solution import ...`. This is a real, load-bearing fact for L4:
  **any RenderPlan/agent prompt that asks for `run_tests()`-compatible test code must tell the
  model to import from `solution`, not `code`.**
- **`workspace_for()`'s 0700 permission bit doesn't survive contact with a fixed-uid
  container on this dev machine.** The sandbox container always runs as `user="10001:10001"`
  (per `sandbox/Dockerfile`'s `useradd -u 10001`), but this dev machine's host Python process
  runs as a normal macOS user account (not uid 10001), so a workspace directory created 0700 by
  that account is completely inaccessible to the container (`Permission denied` on every file
  open, confirmed via the first failing test run). Docker bind mounts never remap UIDs. Widened
  `workspace_for()` to `chmod 0777` after creation — the 0700 spec is the *correct* design for
  a deployment where the host service runs as the same uid the container uses (10001, matching
  the Dockerfile exactly), but this project has no host multi-tenancy to protect against in the
  first place (see CLAUDE.md's forbidden list), so 0777 costs nothing real here. **A future L0
  session should decide whether the real venue deployment runs its host service as uid 10001**
  to restore the tighter 0700 in production — flagged as an open question below rather than
  guessed at.
- gVisor (`runsc`) was installed **inside the colima Linux VM**, not on macOS itself (gVisor
  cannot run on macOS — it intercepts Linux syscalls). This required one apt-repo add + install
  run as root inside the VM (`colima ssh -- sudo ...`), no different in kind from what
  `scripts/00_install_gvisor.sh` already does for the real Ubuntu venue box — this session just
  did the equivalent by hand against a VM instead of running that script (the script assumes a
  real systemd/apt Ubuntu host, which the colima VM's minimal image doesn't fully match).
- Manual verification outside the test suite, before trusting the automated tests: ran
  `docker run --rm --runtime=runsc --network=none -v <workspace>:/work -w /work --user
  10001:10001 --cap-drop=ALL --security-opt no-new-privileges:true sovereign-sandbox:latest
  python /work/main.py` twice by hand — once printing a string (worked), once attempting
  `socket.create_connection(("1.1.1.1", 80))` (got `BLOCKED: OSError`, confirming real network
  isolation under real gVisor, not just `network_mode="none"` on the default `runc` runtime).
  Also confirmed **colima only bind-mounts `/Users` by default, not `/tmp`** — an initial manual
  test using `/tmp/sbtest` as the volume source silently failed inside the VM
  (`can't open file '/work/main.py'`) because `/tmp` isn't in colima's virtiofs mount list.
  `SETTINGS.paths.workspaces` already resolves under the repo (`/Users/...`), so this doesn't
  affect the real code path — only would have affected a naive manual test, caught before it
  became a false negative.
- `verify_calculation()`'s dual-path design choice (documented in the function's own
  docstring): Path A (pint) normalises every result to *base* SI units before comparing; Path B
  (sympy) is deliberately unit-naive (raw substitution). This means a variable declared in a
  non-base unit (kilometres, minutes, etc.) will **always** disagree with Path B unless the
  caller already normalised it — this isn't a bug, it's the entire point: `verify_calculation`
  exists to catch exactly the class of error where a unit conversion was silently dropped
  somewhere upstream. `test_verify_calculation_flags_unit_mismatch` exercises this directly
  (1 km declared vs. raw substitution of `1` → base-units mismatch, `agree=False`).
  `test_verify_calculation_agrees_on_simple_case` uses already-base units (newton, meter²) so
  both paths land on the same number.
- `eval()` is used internally in `verify_calculation()`'s Path A to evaluate `expression`
  against pint `Quantity` objects (pint has no separate string-expression parser of its own —
  arithmetic on `Quantity` is done via normal Python operators). Restricted to
  `{"__builtins__": {}}` with only the caller's declared variables in scope. This function is
  not sandboxed in a container (unlike `run_python`/`run_tests`) — it's a narrow, host-side
  math evaluator over agent-declared numeric expressions, not general code execution; per the
  doc's own pseudocode, `verify_calculation` never calls `docker.from_env()`.
- `pint`, `sympy`, `openpyxl`, and `docker` (the Python SDK, already pinned in the top-level
  `requirements.txt` from Session 0/1 but never installed here until now) were `pip install`ed
  into `.venv` for this session — same pattern as every prior session installing what its own
  layer needs. **`pint`/`sympy` are not in the top-level `requirements.txt`** (only in
  `sandbox/requirements.txt`, for the container) even though `core/sandbox.py`'s
  `verify_calculation()` genuinely needs them on the **host** too, since it runs outside the
  container. Left `requirements.txt` untouched since it isn't in this layer's "Files You Own" —
  flagged as an open question below rather than edited unilaterally.

**Deviations from the doc (and why):**
- `config.yaml`'s `sandbox.runtime` changed from `runc` to `runsc` — not a deviation from the
  doc's *design* (the doc explicitly wants `runsc`, with `runc` only as "the documented
  fallback" when gVisor is genuinely unavailable), just an update to reflect that gVisor is now
  genuinely available and verified on this dev machine, unlike every previous session's actual
  macOS-only environment. `config.yaml` isn't in this layer's owned-files list, but the change
  is a single data value directly about this layer's own behavior, not a redesign of another
  layer.
- `run_tests()` writes the code module as `solution.py`, not the doc's literal `code.py` — see
  Surprises above (`code.py` collides with Python's stdlib `code` module and silently breaks
  every test run). The doc's function signature, file layout (`test_code.py`), and pytest
  invocation (`pytest -q test_code.py`) are otherwise followed exactly.
- `workspace_for()` widens permissions to 0777 after the required 0700-mode creation — see
  Surprises above (fixed-uid container vs. non-matching host uid on this dev machine). The
  `mkdir(mode=0o700, ...)` call itself is unchanged from the doc's literal instruction; only an
  additional `chmod(0o777)` was added afterward, with the full reasoning as an inline docstring
  comment (a genuine hidden-constraint WHY, not a routine change).
- `tests/test_sandbox.py` has **no `@pytest.mark.integration` markers**, unlike the doc's
  illustrative snippet (which shows the decorator once, above `test_hello_world_runs`). Since
  this session has a real, working Docker+gVisor backend for the whole session, every test in
  the file runs and passes for real under the literal DoD command `pytest tests/test_sandbox.py
  -v` with no special flags — marking any of them `integration` would make `pytest.ini`'s
  default `addopts = -m "not integration"` silently *deselect* them under that exact command,
  which would contradict the DoD's explicit "all tests pass including the network and
  path-traversal tests." A future session running on a machine without Docker available at all
  would need to either start one (e.g. colima, as this session did) or accept that this file's
  tests won't collect meaningfully — that tradeoff was made deliberately, in favor of a
  genuinely-verified DoD over a conveniently-skippable one.

### Open questions
- **Should the real venue deployment run its host service (whatever process calls
  `workspace_for()`/`fs_write`/etc.) as uid 10001**, matching `sandbox/Dockerfile`'s
  `useradd -u 10001`, so `workspace_for()` can go back to a strict 0700 in production? Not
  decided here — this session's 0777 workaround is specifically because *this dev machine's*
  host process uid doesn't match, which may or may not be true on the venue box depending on
  how L0's `scripts/03_start_services.sh` ends up launching the FastAPI/agent process.
- **`pint`/`sympy` are real host-side runtime dependencies of `core/sandbox.py`
  (`verify_calculation()`) but are absent from the top-level `requirements.txt`** (only present
  in `sandbox/requirements.txt`, the container's own deps). Not added this session since
  `requirements.txt` isn't in L5's "Files You Own" list — whoever next touches
  `requirements.txt` (or a future patch session) should add `pint==0.24.4` and `sympy==1.13.3`
  to it.

### Next action
Session 5 — L3 Document Ingestion — start with `classify()` in `core/ingest.py`.

## Session 5 — L3 Document Ingestion — 2026-08-29

**Status:** complete. Built exactly to `docs/L3_INGESTION.md`'s file scope (`core/ingest.py`,
`tests/test_ingest.py`, `tests/fixtures/`) with the required API (`classify`, `ingest`,
`_ingest_native`, `_ingest_scanned`, `_OcrBlock`, `_OcrPage`, `page_image_path`, `crop_span`).
Both extraction paths ran for real on this machine — Docling for the native PDF (fully local,
no network once its layout model was cached) and a real live OCR model call through
`core.serving.complete_structured` for the scanned PDF and the drawing image (this profile's
`SETTINGS.ocr_model_id = "gemma4-e2b-ocr"`, an Ollama-served general vision model standing in
for real PaddleOCR-VL, per PATCH 02's local-profile substitution — same pattern as every other
role in this profile). `extractor` is still hardcoded to the literal string `"paddleocr-vl"` in
every OCR-path span regardless of which model actually answered, per the doc's explicit
required output and per `core/schemas.py`'s own comment listing it as one of three fixed
*extraction-method* labels (`"docling" | "paddleocr-vl" | "native"`), not a model-registry id —
this keeps R4 profile-swapping and the recorded provenance label orthogonal, exactly like L2's
router already treats `router_model_id` separately from what a route decision records.

**Files created/changed:** `core/ingest.py` (new), `tests/test_ingest.py` (new),
`tests/fixtures/inspection_native.pdf`, `tests/fixtures/inspection_scanned.pdf`,
`tests/fixtures/drawing_psv2204.png` (all new, generated by a one-off script kept in the
session scratchpad, not committed — the fixtures themselves are committed, the generator isn't
part of this layer's owned files).

**Definition of Done — both commands run for real, output pasted verbatim:**

`pytest tests/test_ingest.py -v` →
```
collected 10 items / 1 deselected / 9 selected

tests/test_ingest.py::test_classify_native_pdf PASSED                    [ 11%]
tests/test_ingest.py::test_classify_scanned_pdf PASSED                   [ 22%]
tests/test_ingest.py::test_classify_image PASSED                         [ 33%]
tests/test_ingest.py::test_bboxes_are_normalised PASSED                  [ 44%]
tests/test_ingest.py::test_span_ids_are_unique_and_wellformed PASSED     [ 55%]
tests/test_ingest.py::test_page_images_rendered_for_every_page PASSED    [ 66%]
tests/test_ingest.py::test_low_confidence_marks_needs_review PASSED      [ 77%]
tests/test_ingest.py::test_blocks_to_spans_normalises_pixel_coordinates PASSED [ 88%]
tests/test_ingest.py::test_crop_span_produces_nonempty_image PASSED      [100%]

================ 9 passed, 1 deselected, 14 warnings in 15.80s =================
```
The one deselected test is `test_scanned_pdf_extracts_known_tag`, marked
`@pytest.mark.integration` exactly as `docs/L3_INGESTION.md`'s test list literally shows (this
is the one doc, unlike L5's, that puts the decorator on an unambiguous, single, explicitly-named
test — no interpretation needed, so it was kept marked even though a live OCR backend was in
fact available all session). Ran it explicitly too, for real, before trusting it:
`pytest tests/test_ingest.py -v -m integration` → `1 passed, 9 deselected in 42.36s`.

Second DoD command, exact script from the doc, run for real:
```
$ python -c "
from pathlib import Path
from core.ingest import ingest
ref, spans = ingest(Path('tests/fixtures/inspection_scanned.pdf'))
print(ref.kind, ref.page_count, len(spans))
print(spans[0].model_dump_json(indent=2))
"
DocKind.SCANNED_PDF 1 7
{
  "span_id": "inspection-scanned-44cf#p1.b1",
  "doc_id": "inspection-scanned-44cf",
  "page": 1,
  "bbox": [
    0.25333333333333335,
    0.0703030303030303,
    0.5301960784313725,
    0.08545454545454545
  ],
  "text": "INSPECTION REPORT (SCANNED COPY)",
  "confidence": 0.99,
  "extractor": "paddleocr-vl",
  "needs_review": false
}
```
Matches every substantive requirement (scanned classification, real page count, non-zero span
count, normalised bbox, `extractor='paddleocr-vl'`) with one cosmetic note: `print(ref.kind)`
prints `DocKind.SCANNED_PDF`, not the bare string `scanned_pdf` the doc's prose names — this is
`core/schemas.py`'s frozen `class DocKind(str, Enum)` definition's own `__str__` behavior (a
classic `(str, Enum)` mixin's `str()` returns `"ClassName.MEMBER"`, not the plain value, on this
Python 3.12), not an L3 bug or a deviation in this layer's code. `ref.kind == DocKind.SCANNED_PDF`
and `ref.kind.value == "scanned_pdf"` are both true — the classification itself is correct,
only the literal printed spelling in the doc's prose doesn't match a frozen-contract enum's
default `str()`. Not fixed (core/schemas.py isn't owned by this layer).

**Observed chars-per-page (the classification signal):**
- `inspection_native.pdf` (2 pages, real PyMuPDF text insertion): `[430, 327]`, mean **378.5** →
  well above the 100-char threshold → `NATIVE_PDF`, correct.
- `inspection_scanned.pdf` (1 page, image-only, no text layer at all): `[0]`, mean **0.0** → far
  below the threshold → `SCANNED_PDF`, correct. (`drawing_psv2204.png` isn't a PDF, so the
  chars-per-page rule doesn't apply — extension routing sends it straight to `IMAGE`.)

**OCR latency per page, measured live against this profile's real model
(`gemma4-e2b-ocr` → Ollama `gemma4:e2b`, the same "thinking"-preamble model PATCH 02 already
flagged as slow):**
- Scanned PDF, page 1, first call (model not recently used, effectively cold): **58.0 s**.
- Scanned PDF, page 1, second call (model still warm from the first): **39.4 s**.
- Drawing image, single page (warm): **21.7 s**.
- This is dramatically slower than L5's gVisor cold-start (~340 ms) — OCR/vision inference is
  clearly the dominant latency in this pipeline on this hardware, not container startup. A
  multi-page scanned document should be budgeted at roughly **20–60 s per page** on this profile
  and this machine; the real `PaddleOCR-VL` model on the venue box's dedicated GPU should be
  substantially faster (it's a purpose-built OCR/layout model, not a general 2B chat model with
  a hidden reasoning preamble), but that is unverified — same platform-gap caveat as every prior
  session's model-latency numbers.

**Handwriting confidence range:** **not observed from a live model** — no handwriting fixture
was in scope for this session (the doc's required fixtures are a native PDF, a scanned PDF, and
a drawing image; none call for actual handwriting). The two real OCR calls this session made
(scanned PDF, drawing image — 10 blocks total) came back at a uniform **confidence 0.99** on
every block, because all of the source text is clean printed text, not handwriting — there was
never a genuine opportunity for the model to report low confidence. The `needs_review=True`
gating path itself is real and correct (`if confidence < SETTINGS.agent.ocr_review_threshold`,
0.75 from `config.yaml`), but it is only exercised here by
`test_low_confidence_marks_needs_review`, a synthetic unit test that constructs a fake
`_OcrPage` with a deliberately low `confidence=0.4` block and asserts `needs_review is True` —
not a claim about what a real handwriting sample would score. **A future session with a genuine
handwritten fixture should replace this note with a real observed range.**

**Surprises a fresh session must know:**
- **Docling 2.15.0's pinned dependency range let pip resolve an incompatible `docling-core`.**
  `docling==2.15.0` declares `docling-core[chunking]>=2.13.1,<3.0.0` with no tighter upper
  bound; a fresh `pip install docling==2.15.0` today (2026-08-29, well over a year after that
  release) pulled `docling-core==2.84.0`, which has since removed
  `docling_core.types.legacy_doc.base.BoundingBox` — an internal name docling 2.15.0's own
  `ds_glm_model.py` still imports at module load, so **`from docling.document_converter import
  DocumentConverter` failed outright** (`ImportError`) before any code in this layer even ran.
  Fixed by pinning `docling-core==2.15.1` (closest release to docling's own version number) in
  `.venv` — this produces one `pip` dependency-conflict warning
  (`docling-ibm-models 3.15.0 requires docling-core<3.0.0,>=2.33.0`) that is **cosmetic**: the
  actual code paths this layer exercises (`DocumentConverter`, `PdfPipelineOptions`,
  `DoclingDocument.texts`/`.pages`, `BoundingBox.to_top_left_origin`/`.normalized`) all work
  correctly with `docling-core==2.15.1` — confirmed by every test in this session passing for
  real, not just importing cleanly. **Neither `docling` nor `docling-core` version is pinned in
  the top-level `requirements.txt`** beyond `docling==2.15.0` itself — a future session that
  runs `pip install -r requirements.txt` fresh will hit this exact same failure unless
  `docling-core==2.15.1` is added explicitly. Flagged as an open question below rather than
  edited unilaterally (`requirements.txt` isn't in this layer's "Files You Own").
- **Docling's default pipeline runs EasyOCR internally and downloads its weights over the
  network on first use — confirmed by directly observing the download** ("Downloading detection
  model...", "Downloading recognition model...") the first time this session called `.convert()`
  with default options. `PdfPipelineOptions.do_ocr` defaults to `True`, and its default
  `ocr_options` is `EasyOcrOptions`. EasyOCR is explicitly on `CLAUDE.md`'s forbidden list, and
  a network download at any point in this pipeline is exactly the kind of thing R1 forbids at
  runtime. Fixed by constructing the converter with **`PdfPipelineOptions(do_ocr=False,
  do_table_structure=True)`** explicitly — native/office documents already have a text layer,
  so OCR was never needed on this path anyway, but the default would have silently pulled in
  the forbidden dependency's weights regardless. **Any future code that builds its own
  `DocumentConverter` must keep `do_ocr=False`** — this is now the single most
  easily-reintroduced drift risk in this layer.
- **Real, measured finding: this profile's substitute OCR model does not reliably follow the
  prompt's "0..1 normalised" bbox instruction.** The first live call against the scanned PDF
  fixture returned all 7 blocks with bbox values like `(323.0, 116.0, 676.0, 141.0)` — raw pixel
  coordinates matching the 1275×1650px rendered page image, not normalised floats. Every block
  was silently dropped by the degenerate-bbox guard before a fix was in place (0 spans
  extracted from a real 7-block page). This is a real difference between a general vision-chat
  model repurposed for OCR (this local profile) and a purpose-built grounding/OCR model like
  real PaddleOCR-VL, which is trained specifically to emit accurate normalised regions. **Fixed
  with `_coerce_to_normalised()`** — a deterministic unit conversion (divide by the known image
  pixel dimensions) applied only when a block's bbox values exceed 1.001, i.e. are obviously in
  pixel space. This never touches extracted *text*, so it is not a "second-LLM cleanup pass" in
  the sense the doc's drift tripwires forbid (that rule is about not letting a model rewrite
  content it already extracted) — it is coordinate-unit bookkeeping on numbers the model already
  returned. `test_blocks_to_spans_normalises_pixel_coordinates` is a permanent regression test
  for this. **This finding should inform L4/L7's UI**: bbox precision (not just confidence) may
  be noticeably worse on this local dev profile than on the real venue PaddleOCR-VL deployment,
  independent of the `needs_review` confidence flag — the model here reports high confidence
  (0.99) even on blocks whose *coordinates* needed silent unit correction.
- **`docling-ibm-models`'s table-image generation option is deprecated in the `docling-core`
  version now installed**, producing a harmless `DeprecationWarning` on every native-PDF
  conversion (`generate_table_images` → `generate_page_images` + `TableItem.get_image()`). Not
  acted on — `do_table_structure=True` still works correctly for this session's fixtures (no
  tables in them), and chasing a deprecation warning in a pinned-for-compatibility dependency is
  out of this layer's scope.
- `Path.stem`-derived `doc_id` slugs collide harmlessly across repeated `ingest()` calls on the
  same fixture within one session (each call mints a fresh 4-hex suffix via `uuid.uuid4()`, per
  `01_CONTRACTS.md`'s `doc_id` convention) — every `page_images/` file this session wrote is
  still on disk under a distinct `{doc_id}_p{page:03d}.png` name; nothing was cleaned up
  automatically (no test fixture teardown removes them, unlike L5's `workspace_for` cleanup),
  consistent with `data/` being fully gitignored runtime state.
- Scanned-PDF fixture generation: an initial version rendered the page at 1700×2200 and saved
  it losslessly into the PDF, producing an **11 MB** fixture — far too large to commit. Reduced
  to 1000×1300 and JPEG quality 85 for the embedded page image, bringing the final
  `inspection_scanned.pdf` down to **56 KB** while remaining fully legible (verified visually
  before trusting it for the live OCR regression test — the rendered "V-101" line is crisp at
  150 DPI).

**Deviations from the doc (and why):**
- `extractor` is a hardcoded literal `"paddleocr-vl"` string constant in every OCR-path span,
  not derived from `SETTINGS.ocr_model_id` — see the paragraph at the top of this entry.
  Matches the doc's explicit required output (`extractor='paddleocr-vl'`) and
  `core/schemas.py`'s own comment describing `extractor` as one of three fixed extraction-method
  labels, not a model registry id.
- `PdfPipelineOptions(do_ocr=False, ...)` is an explicit addition beyond the doc's one-line
  `_ingest_native` docstring — necessary to keep Docling off the forbidden-EasyOCR path; see
  Surprises above. Not a deviation from the doc's *intent* (native documents were never meant to
  go through OCR at all), just an explicit guard the doc's pseudocode didn't spell out.
- `_coerce_to_normalised()` is an addition beyond the doc's required API — a deterministic
  pixel→normalised bbox conversion applied before the existing clamp/degenerate-bbox check, not
  a new extraction method or a text-altering step. See Surprises above for the real failure it
  fixes.
- `ingest()` also handles `DocKind.OFFICE` (delegated to `_ingest_native`, since Docling
  genuinely supports docx/xlsx/pptx through the same `DocumentConverter`) and `DocKind.PLAINTEXT`
  (a small dedicated `_ingest_plaintext`, one span per blank-line-separated paragraph, each
  given an equal vertical slice of a synthetic single page) — neither is named in the doc's
  required-function list, neither has a fixture or a test in this session, and neither claims
  more precision than it has (no office-file rasteriser exists in this scope, so `page_count=1`
  and `page_images=[]` for both kinds — documented inline as an approximation, not silently).
  Added only because `classify()`'s own routing table lists all five `DocKind` values as valid
  `ingest()` targets; leaving two of them unhandled would make `ingest()` raise on a valid
  `DocKind` the same module produces.

### Open questions
- **`docling-core` needs an explicit compatible pin.** `requirements.txt` currently only has
  `docling==2.15.0` with no `docling-core` line at all, so a fresh install resolves the latest
  `docling-core` (2.84.0 as of this session) and fails to import — see Surprises. Whoever next
  touches `requirements.txt` should add `docling-core==2.15.1` (or re-verify against a newer
  `docling` release if this project ever moves off `2.15.0`). Not edited this session —
  `requirements.txt` isn't in L3's "Files You Own" list, same reasoning as L5's `pint`/`sympy`
  gap two sessions ago.
- **No handwriting fixture exists anywhere in this repo yet.** R8 explicitly names handwriting
  as in scope, and the `needs_review` gate is real and tested at the unit level, but nothing in
  this project has ever run a genuine handwritten sample through the live OCR path. A future
  session (or the demo prep itself) should add one and record a real observed confidence range,
  replacing the placeholder note above.
- **Bbox precision on this local dev profile is measurably worse than confidence scores alone
  would suggest** (see the pixel-coordinate finding in Surprises) — worth a note to whoever
  builds L7's evidence-panel UI: don't treat `needs_review=False` as "the highlighted region is
  exactly right" on this profile. This may or may not hold on the real venue PaddleOCR-VL
  deployment; unverified either way.

### Next action
Session 6 — L6 Knowledge Base — start with `ensure_collection()` in `core/kb.py`.

## Session 5b — L3 Re-verification — 2026-09-02

**Status:** complete — no code changes. This session was asked to build L3 fresh, but
`core/ingest.py`, `tests/test_ingest.py`, and `tests/fixtures/` already existed from Session 5
(2026-08-29) and matched `docs/L3_INGESTION.md`'s required API exactly (`classify`, `ingest`,
`_ingest_native`, `_ingest_scanned`, `_OcrBlock`, `_OcrPage`, `page_image_path`, `crop_span`, the
verbatim OCR prompt, `needs_review` gating). Per CLAUDE.md's "verification is not optional" rule,
this session re-ran the full Definition of Done live rather than trusting the prior log, including
the `@pytest.mark.integration` test, which needed the Ollama server started fresh
(`nohup ollama serve &` — it was not running at session start). Zero files touched.

**Definition of Done — re-run live, output pasted verbatim:**

`pytest tests/test_ingest.py -v` →
```
9 passed, 1 deselected, 14 warnings in 16.45s
```
All 9 unit tests green, unchanged from Session 5.

`pytest tests/test_ingest.py -v -m integration` →
```
tests/test_ingest.py::test_scanned_pdf_extracts_known_tag PASSED           [100%]
1 passed, 9 deselected, 6 warnings in 45.00s
```
V-101 survived verbatim through a real live OCR call — the regression test that protects
against a model "correcting" a tag number. 45s wall time for one page, consistent with Session
5's 39–58s/page range for this profile's substitute OCR model (`gemma4-e2b-ocr` →
Ollama `gemma4:e2b`).

Second DoD command, exact script from the doc:
```
$ python -c "
from pathlib import Path
from core.ingest import ingest
ref, spans = ingest(Path('tests/fixtures/inspection_scanned.pdf'))
print(ref.kind, ref.page_count, len(spans))
print(spans[0].model_dump_json(indent=2))
"
DocKind.SCANNED_PDF 1 8
{
  "span_id": "inspection-scanned-a7c9#p1.b1",
  "doc_id": "inspection-scanned-a7c9",
  "page": 1,
  "bbox": [0.25333333333333335, 0.0703030303030303, 0.5301960784313725, 0.08545454545454545],
  "text": "INSPECTION REPORT (SCANNED COPY)",
  "confidence": 0.99,
  "extractor": "paddleocr-vl",
  "needs_review": false
}
```
All required fields correct: scanned classification, real page count, non-zero span count
(8, vs. Session 5's 7 — the OCR model is non-deterministic across calls, expected), normalised
bbox, `extractor='paddleocr-vl'`. Matches Session 5's finding exactly on the cosmetic
`DocKind.SCANNED_PDF` vs. `"scanned_pdf"` `str()` note (frozen `core/schemas.py` enum behavior,
not an L3 bug).

**Surprises a fresh session must know:**
- Ollama was not running at session start (`curl 127.0.0.1:11434` connection refused) despite
  Session 5/PATCH 02 having used it live — it is still not a persistent `brew services`-managed
  daemon on this machine, exactly as PATCH 02 flagged. Started manually this session via
  `nohup ollama serve &`; a future session should expect to do the same unless someone converts
  it to a managed service.
- OCR span count is not stable across runs against the same fixture (7 blocks in Session 5,
  8 here) — the substitute vision-chat OCR model's segmentation of the scanned page varies
  slightly call to call, even though the load-bearing regression assertion (V-101 survives
  verbatim) held both times. Worth remembering if a future test ever asserts an exact span
  count against this fixture instead of `> 0` — it would be flaky by design of the current
  local-profile model, not a bug in `core/ingest.py`.

**Deviations from the doc (and why):** none — no code was written this session.

### Open questions
- _(none new — all open questions from Session 5 stand: `docling-core` needs an explicit pin
  in `requirements.txt`, no handwriting fixture exists yet, bbox precision on this local profile
  is worse than confidence scores alone suggest)_

### Next action
Session 6 — L6 Knowledge Base — start with `ensure_collection()` in `core/kb.py`.

## Session 6 — L6 Knowledge Base — 2026-09-02

**Status:** complete — every function built to the doc's exact signatures, all 10 required
tests pass for real against a live Qdrant and a live embedding endpoint on this machine (no
mocks), `scripts/index_corpus.py` really ingested all 3 `tests/fixtures` files, and the DoD's
final `search()` command returns the literal tag with `matched_by="both"`. One real bug found
and fixed along the way (doc_id instability causing duplication on reindex — see below).

**Files created/changed:** `core/kb.py`, `scripts/index_corpus.py`, `tests/test_kb.py` (all
new, per this layer's "Files You Own" list — no other layer's files touched).

**Blocker hit and resolved before any code was written:** `docs/L6_KB.md` specifies
`SentenceTransformer(SETTINGS.embedding_model_path)`, i.e. a pre-staged local
sentence-transformers directory. No such directory exists on this dev machine
(`config.yaml`'s `embedding_model_path` points at `./models/embeddinggemma-300m`, which
doesn't exist — `models/` isn't even created). Attempting to download `BAAI/bge-m3` (the
doc's named example model) from HuggingFace to stage it was **correctly blocked by the auto
mode classifier** as a network fetch of model weights — exactly the R1 violation this
project's non-negotiables forbid, working as intended, not a bug to route around. Asked the
user how to proceed; they chose to embed via the already-local, already-staged
`embeddinggemma-300m` Ollama model (PATCH_02's manifest, `manifests/embeddinggemma-300m.yaml`,
serving on `http://127.0.0.1:11434/v1`) instead of sentence-transformers. `core/kb.py`'s
`_embed()` calls that manifest's OpenAI-compatible `/v1/embeddings` endpoint via `REGISTRY.get()`
(read-only import from `core.serving`, L1's file untouched) rather than loading a local
sentence-transformers model directly. **This is a deviation from the doc's literal text,
recorded per CLAUDE.md's session protocol** — the dense vector size is read from the model at
runtime (`_embedding_dim()`, a one-time probe embed call, cached) rather than hardcoded to
BGE-M3's 1024d, so the collection sizes itself correctly either way (measured: 768d for
embeddinggemma). Zero network calls happen in either design; the constraint that forced this
choice was "no download **right now**," not the underlying air-gap requirement, which both
designs satisfy identically once a model is actually staged.

**Real infrastructure stood up this session (not simulated):** this dev machine had no Docker
daemon reachable at session start (`colima` wasn't running — see Session 1/4's platform-gap
notes). Ran `colima start` (macOS Virtualization.Framework backend) — succeeded for real this
time — then `docker run -d -p 127.0.0.1:6333:6333 -v ./data/qdrant:/qdrant/storage
qdrant/qdrant:v1.12.0`. Installed `qdrant-client==1.12.1` and `sentence-transformers==3.3.1`
into `.venv` (both already pinned in `requirements.txt` since Session 0; sentence-transformers
ended up unused by the final design but was installed before the embedding-backend decision was
made and left in place since it's an already-pinned dependency, not a scope violation).

**Design decisions beyond the doc's literal text:**
- **Sparse half: Qdrant's server-side IDF modifier**, not a client-side BM25 library (the doc
  offered either; picking one and documenting it was explicitly required). Tokenizer is a
  small dependency-free regex (`[a-zA-Z0-9][a-zA-Z0-9-]*`, lowercased) that deliberately keeps
  hyphenated identifiers like `V-101`/`PSV-2204` as single tokens — splitting on `-` would be
  exactly the bug this layer exists to avoid. Each token is hashed to a sparse-vector index via
  `zlib.crc32` (deterministic across processes/machines, unlike Python's salted `hash()`), with
  raw term-frequency counts as values; `SparseVectorParams(modifier=Modifier.IDF)` on the
  collection does the actual BM25-style weighting server-side.
- **`matched_by` labeling requires two extra one-shot queries** (`dense`-only and `sparse`-only,
  same vectors, `with_payload=False`) run alongside the real fused `prefetch`+RRF query, purely
  to determine which retriever(s) actually contributed a given fused hit — Qdrant's fused
  response doesn't expose this by construction. Three round-trips per `search()` call instead
  of one; acceptable at this project's demo scale (R11), not something to optimize away.
- **`exact=True` (`SearchParams`) on every dense/sparse query in `search()`**, not the HNSW
  default. Found empirically: with approximate search, filtered-ANN recall degraded as the
  shared local "spans" collection accumulated points across repeated test/debug runs, which
  **flipped a close ranking assertion nondeterministically** (same fixture, same query, ~30%
  flip rate across repeated runs — reproduced and diagnosed live, not assumed). At this
  project's real scale (one plant's manuals/SOPs/correspondence on a single Qdrant node), exact
  brute-force search is cheap and removes this whole class of nondeterminism.
- **`score_threshold` on the sparse side of both the standalone sparse query and the sparse
  `Prefetch`.** Found empirically: Qdrant pads a small filtered candidate set up to `limit` even
  with zero true lexical overlap, and RRF then gives that zero-overlap document real fusion
  credit for a "rank" it never earned — this was the second, harder-to-spot cause of the same
  flaky ranking above (diagnosed by dumping raw dense/sparse scores per candidate; a "sparse
  score" of exactly `0.0` was being included in RRF's rank computation). Excluding it fixed the
  flake outright (8/8 clean reruns after the fix, vs. failing on repeat before). Also discovered
  along the way: Qdrant's IDF modifier can legitimately return a **negative** score once a term
  appears in more than half the (tiny test) corpus — correct classic-BM25 behaviour, harmless at
  real corpus scale, but a trap for a small local Qdrant instance carrying leftover points from
  prior manual exploration. Fixed by having `tests/test_kb.py` drop and recreate the whole
  `spans` collection at module start (`_isolated_collection` fixture) — safe because this is a
  local single-tenant dev Qdrant with no real corpus loaded yet, and `scripts/index_corpus.py`
  is the thing that actually (re)builds the real KB, run separately afterward.
- **Real bug found and fixed in `scripts/index_corpus.py`:** `core.ingest.ingest()` assigns a
  **random** `doc_id` (4 hex from `uuid4()`) unless one is passed explicitly — fine for a
  one-off upload, but fatal for a corpus connector whose entire job is "re-ingesting a document
  updates in place instead of duplicating" (this is the property `core/kb.py`'s point-id
  determinism exists to provide, and it only works if `span_id`, and therefore `doc_id`, is
  stable across runs). First `--force` reindex of the same 3 fixture files **doubled** the
  collection (3→6 documents, 21→42 spans) because each file got a fresh random `doc_id` every
  run. Fixed by adding `_stable_doc_id()` to the script — same slug convention as
  `core.ingest._make_doc_id`, but the 4-hex suffix is `sha1(resolved_path)[:4]` instead of
  random, so the same file path always produces the same `doc_id`, and `ingest(path,
  doc_id=_stable_doc_id(path))` is called explicitly. Confirmed fixed: repeated `--force` runs
  now stay at 3 documents / 21 spans.

**Definition of Done — every command run for real:**

`pytest tests/test_kb.py -v` (bare, as literally specified) →
```
collected 10 items / 10 deselected / 0 selected
========================= 10 deselected in 0.48s =========================
```
Deselected by `pytest.ini`'s repo-wide `addopts = -m "not integration"` — same pattern as every
prior session's live-model-dependent tests (L1/L2/L3). The real proof is the explicit opt-in:

`pytest tests/test_kb.py -v -m integration` →
```
collected 10 items
tests/test_kb.py::test_ensure_collection_idempotent PASSED               [ 10%]
tests/test_kb.py::test_index_then_get_span_roundtrip PASSED              [ 20%]
tests/test_kb.py::test_reindex_same_doc_does_not_duplicate PASSED        [ 30%]
tests/test_kb.py::test_hybrid_finds_exact_tag PASSED                     [ 40%]
tests/test_kb.py::test_hybrid_finds_paraphrase PASSED                    [ 50%]
tests/test_kb.py::test_dense_only_would_miss_tag PASSED                  [ 60%]
tests/test_kb.py::test_filter_by_doc_ids PASSED                          [ 70%]
tests/test_kb.py::test_get_span_missing_raises PASSED                    [ 80%]
tests/test_kb.py::test_get_span_never_fuzzy_matches PASSED               [ 90%]
tests/test_kb.py::test_stats_reports_counts PASSED                       [100%]
========================== 10 passed in 1.14s ===========================
```
Reran 8 times consecutively after the `exact=True` + `score_threshold` fixes above: 8/8 clean.
Before those fixes: failed roughly 1 run in 3, always on the same close-ranking assertion —
recorded here so nobody "fixes" this test file back into that state by relaxing search_params.

`python scripts/index_corpus.py --dir tests/fixtures --recursive` (fresh state) →
```
[1/3] drawing_psv2204.png: indexed 3 spans as drawing-psv2204-055c (22.x s, live OCR call)
[2/3] inspection_native.pdf: indexed 10 spans as inspection-native-b41a (4.6s, Docling)
[3/3] inspection_scanned.pdf: indexed 8 spans as inspection-scanned-7908 (28.4s, live OCR call)
------------------------------------------------------------------
file                    status                             spans
------------------------------------------------------------------
drawing_psv2204.png     indexed (drawing-psv2204-055c)     3
inspection_native.pdf   indexed (inspection-native-b41a)   10
inspection_scanned.pdf  indexed (inspection-scanned-7908)  8
------------------------------------------------------------------
total spans indexed this run: 21
```
Re-run with no flag → all 3 report `skipped (unchanged)`, 0 spans this run (mtime+size check
live). Re-run with `--force` → re-indexes all 3, **same 3 doc_ids as the first run**, collection
stays at 3 documents / 21 spans (the bug-fix above, confirmed).

`python -c "from core.kb import search, stats; ..."` (exact DoD snippet) →
```
{'documents': 3, 'spans': 21, 'collection_status': 'green'}
1.0   both inspection-native-b41a#p2.b3   All readings are above the minimum required thickness of 10.5 mm per t
0.583 both inspection-scanned-7908#p1.b3  Vessel Tag: V-101
0.476 both inspection-native-b41a#p2.b2   Shell thickness readings (mm): Point 1: 12.4   Point 2: 12.3   Point 3
```
Rank 2 contains the literal tag `V-101` (from the scanned-PDF OCR path — same fixture Session 5
proved recovers `V-101` verbatim) with `matched_by="both"` — satisfies the DoD's requirement
that the lexical half be demonstrably live, and shows dense+sparse fusion actively agreeing here
rather than sparse alone carrying it.

**Collection size after indexing fixtures:** 3 documents, 21 spans (rank-1 result score 1.0 is
an exact self-similarity artifact of the paraphrase-style query overlapping heavily with that
span's own wording — expected, not a bug).

**Embedding load time (measured on this machine, embeddinggemma-300m via Ollama):** module
import (`from core.kb import _embed`, no network call yet): **0.50s**. First real embed call
(cold — triggers Ollama to load the model into memory): **0.90s**. Second embed call (model
already warm): **0.03s**. This is far faster than a from-scratch sentence-transformers
`.from_pretrained()` load would be, since Ollama keeps the model resident between calls per its
own `OLLAMA_KEEP_ALIVE` setting (see PATCH_02).

**Sparse vector implementation:** Qdrant's built-in **IDF modifier** (server-side), not a
client-side BM25 library — see "Design decisions" above for the full reasoning and the two real
bugs this choice surfaced (zero-score padding contributing to RRF; negative IDF on an
almost-empty test corpus). No `fastembed`/`bm25` dependency added.

**Surprises a fresh session must know:**
- `core/kb.py`'s embedding backend is **not** the doc's literal `SentenceTransformer` line —
  see the blocker section above. If a real local sentence-transformers model ever gets staged
  on the venue box (matching the doc exactly), only `_embed()`/`_embed_manifest()` /
  `_embedding_dim()` need to change; the rest of the module (Qdrant schema, sparse tokenizer,
  fusion, `get_span`, `stats`) is backend-agnostic.
- `_isolated_collection` (autouse, module-scoped in `tests/test_kb.py`) **drops and recreates
  the entire `spans` collection** before this test file's tests run. Anyone running
  `scripts/index_corpus.py` and then the test suite in the same session (as this session did,
  more than once) will find the real corpus wiped by the next `pytest -m integration` run —
  this is intentional (see "Design decisions" above) but easy to forget before a demo. **Always
  run `index_corpus.py` last**, after any test runs, not before.
- This session started `colima` fresh (it was not running at session start) and it did **not**
  have the `runsc` gVisor runtime registered — confirmed by running `tests/test_sandbox.py`
  (L5, not this layer) with `DOCKER_HOST` set: it got past "docker daemon unavailable" to
  `unknown or invalid runtime name: runsc`. This is an L0/L5 environment fact orthogonal to L6
  (Session 4's earlier colima+runsc setup apparently did not persist across sessions on this
  machine), not a regression introduced here — recorded for whichever session next touches the
  sandbox.
- `pytest -q` (whole repo) after this session: `10 failed, 52 passed, 14 deselected`. 9 of the
  10 failures are the pre-existing `test_sandbox.py` Docker/runsc gap above (unrelated to L6).
  The 10th, `test_sandbox.py::test_kb_search_delegates_and_fails_loudly_until_l6_exists`, is
  **expected and correct fallout of L6 now existing** — that test's own name says it only holds
  "until l6 exists," exactly like PATCH_02's effect on `test_router.py`'s demo-route tests. Per
  CLAUDE.md, `tests/test_sandbox.py` is L5's file and was not touched; whoever next owns L5
  should update or retire that specific test now that `core.kb.search` is real.

**Deviations from the doc (and why):** the embedding backend (see Blocker section above) is the
only deviation from `docs/L6_KB.md`'s literal text; every function signature, the Qdrant schema
shape, batching, point-id determinism, and the forbidden-list items (no reranker, no
ColPali/ColQwen, no GraphRAG, no Chroma/FAISS swap, no prose from `search()`, no re-chunking)
match the doc exactly.

### Open questions
- _(none new — the embedding-backend deviation above was resolved with the user in-session, not
  deferred)_

### Next action
Session 7 — L7b Deliverable Renderer — start with `validate_plan()` in `core/render.py`.

## Session 7 — L7b Deliverable Renderer — 2026-09-07

**Status:** complete — every function built to the doc's exact signatures, all 14 required
tests pass for real, and the DoD's bare `python -c` script (no pytest, no live services)
produced a real 37.5KB docx, 34.4KB pptx, and 6.7KB xlsx from one sample plan, all opened
back cleanly and inspected. Two real bugs found and fixed along the way (see below).

**Files created/changed:** `core/render.py`, `templates/approval_note_v1.docx`,
`templates/board_deck_v1.pptx`, `tests/test_render.py` (all new, per this layer's "Files You
Own" list). `templates/calc_sheet_v1.xlsx` does **not** exist on disk, per both the doc and the
session prompt — xlsx is built entirely at render time by `_render_xlsx()` via openpyxl.

**Templates that exist:**
- `templates/approval_note_v1.docx` (37,241 bytes) — generated once with python-docx (letterhead
  placeholder, 5 numbered sections, provenance appendix), then rendered at runtime via docxtpl.
  Jinja tags live in single, un-split runs (`add_run()` called once per tag) — the standard
  docxtpl gotcha (Word silently splitting a run mid-tag) never arises because the template was
  built programmatically, not typed by hand in Word.
- `templates/board_deck_v1.pptx` (27,387 bytes) — python-pptx's own default template, saved
  as-is. Deliberately not themed (Drift tripwire: no theming system) — the point of it being a
  file on disk is that the org can later swap in a branded one without touching `core/render.py`,
  which only ever does `Presentation(str(_PPTX_TEMPLATE))` and `slide_layouts[1]` ("Title and
  Content"), same layout for all 5 slide types per the doc.

**This layer needs no live services at all** — deliberately verified. `docs/L7B_RENDERER.md`'s
own MISSION LOCK says "you are NOT building... retrieval," so `tests/test_render.py` patches
`core.render.get_span` (the one name `render.py` imports from `core.kb`) with an in-memory
lookup over 4 fixture `EvidenceSpan`s, applied **at module import time**, not via a pytest
`monkeypatch` fixture — because the DoD's own verification script imports `sample_plan` from
`tests.test_render` and calls `render()` directly from a bare `python -c` invocation, entirely
outside pytest, so the patch has to already be in effect the moment the module loads. Confirmed
this session's colima/Qdrant/Ollama were **all stopped** (per the user's "kill all" request
between the L6 and L7b sessions) for the entire duration of this work — L7b genuinely does not
touch any of that infrastructure, which is exactly the intended separation of concerns.

**Real bugs found and fixed:**
1. **`docxtpl.RichText` silently renders empty**, in every configuration tried (alone in its own
   paragraph, alongside other runs, with `autoescape=True` and without) — reproduced in
   isolation with a 5-line minimal repro before touching the real template, so this is
   confirmed as this environment's actual `docxtpl==0.19.0` behavior, not a template-authoring
   mistake. Root cause not fully chased (would need to trace `RichText.__html__`/Jinja
   `Markup` interaction inside docxtpl's `render_xml_part`), but the doc's own requirement ("no
   `eval()`, no second source of truth") doesn't actually need RichText — replaced the bold
   `DISAGREES — HUMAN REVIEW REQUIRED` banner with a plain **`{% if c.disagreed %}...{% else
   %}...{% endif %}` block**, where the "disagreed" branch's run is pre-formatted bold+red at
   template-build time (`run.bold = True; run.font.color.rgb = RGBColor(0xC0,0x39,0x2B)`) and
   docxtpl only ever chooses which pre-styled literal run survives — never sets formatting
   dynamically. Verified this pattern in isolation first (bold `True`/`None` came back correctly
   for both branches) before adopting it project-wide. **If a future session ever needs dynamic
   per-value rich formatting in a docx template, re-verify `RichText` against whatever
   `docxtpl` version is installed then — do not assume it works from the doc's own example.**
2. **`out.stem` used as `task_id` inside `_build_context()`** — since `render()` renders to a
   *temporary* path (`<slug>.<ext>.tmp` inside the output directory) before the atomic rename,
   `out.stem` at render time was the **random tempfile name**, not the real task_id. First full
   DoD run silently produced `Ref: tmp35sjcew6.docx` and `Receipt:
   tmp35sjcew6.docx.receipt.json` in the rendered document instead of `Ref: t-demo` /
   `Receipt: t-demo.receipt.json` — caught by actually reading the rendered output back, not by
   trusting the file was created. Fixed to `out.parent.name`, since `tempfile.mkstemp(dir=out_dir,
   ...)` places the temp file in the *same* directory as the final file, and that directory is
   always named after `task_id` (`SETTINGS.paths.outputs / task_id / ...`) regardless of which
   of the two paths (temp or final) is passed in — satisfies the doc's fixed
   `_render_docx(plan, spans, out: Path)` signature (no separate `task_id` parameter) without
   inventing one.

**Design decisions beyond the doc's literal text:**
- **`source_note` and the amber `needs_review` marker are derived, not stored** — `GroundedValue`
  and `Finding` (frozen contracts) carry no such fields, so `_build_context()` computes
  `"Doc {doc_id}, p.{page}"` (de-duplicated, order-preserving) from the resolved spans for every
  field/finding, and appends `" [⚠ low-confidence OCR — verify against original]"` when any
  cited span has `needs_review=True`.
- **The `calculations` template context is derived from `plan.fields`, not a separate schema
  field** — `RenderPlan`/`GroundedValue` (frozen) have no `calculations`/`steps`/`verified`
  fields, only `calculation: str | None` (an expression string) and `computed_from`. Any field
  with `computed_from` set is treated as a calculation; `calculation.splitlines()` becomes the
  rendered "steps", and the verdict is read from the text itself — the string `"disagree"`
  (case-insensitive) anywhere in `calculation` triggers the `DISAGREES — HUMAN REVIEW REQUIRED`
  banner, otherwise it renders `AGREES`. This matches the doc's explicit instruction ("L4 will
  have already run `verify_calculation()`... render the steps that came back... do not evaluate
  anything yourself") — the renderer never computes agreement, it only detects a verdict L4 is
  expected to have already written into the expression text.
- **XLSX `Calculations` sheet: one row per step**, with the calculation's label/expression/
  result/unit/verdict repeated on every row for that calculation (not merged cells) — simplest
  to scan, no merged-cell bookkeeping, matches "no theming system, no charts, no layout solver."

**Definition of Done — every command run for real:**

`pytest tests/test_render.py -v` →
```
collected 14 items
tests/test_render.py::test_validate_rejects_field_without_evidence_ref PASSED             [  7%]
tests/test_render.py::test_validate_rejects_unresolvable_span PASSED                      [ 14%]
tests/test_render.py::test_validate_rejects_needs_review_span_in_numeric_field PASSED     [ 21%]
tests/test_render.py::test_validate_allows_needs_review_when_explicitly_confirmed PASSED  [ 28%]
tests/test_render.py::test_validate_requires_calculation_string_when_computed_from_set PASSED [ 35%]
tests/test_render.py::test_validate_needs_review_string_field_is_allowed_without_confirmation PASSED [ 42%]
tests/test_render.py::test_render_fails_closed_leaves_no_file PASSED                      [ 50%]
tests/test_render.py::test_render_is_atomic PASSED                                        [ 57%]
tests/test_render.py::test_docx_contains_provenance_appendix PASSED                       [ 64%]
tests/test_render.py::test_docx_contains_every_finding PASSED                             [ 71%]
tests/test_render.py::test_calculation_disagreement_renders_banner PASSED                 [ 78%]
tests/test_render.py::test_pptx_slide_count_matches_findings_plus_four PASSED             [ 85%]
tests/test_render.py::test_xlsx_has_three_sheets_and_amber_rows PASSED                    [ 92%]
tests/test_render.py::test_file_sha256_stable PASSED                                      [100%]
========================== 14 passed in 1.00s ===========================
```
(One extra test beyond the doc's 13 — `test_validate_needs_review_string_field_is_allowed_
without_confirmation` — added to lock in that the needs_review gate is scoped to numeric fields
only, per the doc's literal wording ("...and the value is numeric..."), not to every field
citing a needs_review span.)

`python -c "from core.render import render; from tests.test_render import sample_plan; ..."`
(exact DoD snippet) →
```
/…/data/outputs/t-demo/v-101-annual-inspection-approval-note.docx 37514
/…/data/outputs/t-demo/v-101-annual-inspection-approval-note.pptx 34402
/…/data/outputs/t-demo/v-101-annual-inspection-approval-note.xlsx 6739
```
All three opened back and inspected for real (not just "file exists"):
- **DOCX** (47 paragraphs): populated PROVENANCE appendix with all 3 resolved fixture spans
  (`[corr-0091#p1.b1] corr-0091 p.1 — "..."`, etc.), both findings present with sources, the
  calculation section shows `Result: 12.35 mm` / `Independent re-derivation: AGREES`, and
  `Ref: t-demo` / `Receipt: t-demo.receipt.json` (confirms bug #2's fix).
- **PPTX** (6 slides): Title → Summary → 2 finding slides → Measured Values → Provenance,
  matching `len(findings) + 4` exactly.
- **XLSX** (3 sheets, `Summary`/`Values`/`Calculations`): dims `A1:B4` / `A1:G5` / `A1:F3`.

**Regression check — whole repo:** `pytest -q` → `9 failed, 67 passed, 14 deselected`. All 9
failures are the pre-existing `test_sandbox.py` Docker/`runsc` gap from Session 6 (colima has no
gVisor runtime registered this session — unrelated to L7b, not touched). Note:
`test_sandbox.py::test_kb_search_delegates_and_fails_loudly_until_l6_exists` now **passes**
again in this run — not because of anything this session did, but because colima/Qdrant were
stopped (user's "kill all" request) between Sessions 6 and 7, so `core.kb`'s connection to
Qdrant fails and that failure happens to surface as a `WorkbenchError` too, satisfying the
test's (now-stale) assertion for an unrelated reason. Flagging for whoever next owns L5: that
test's name and premise ("...until_l6_exists") are permanently outdated now that L6 is real —
its current pass/fail is an accident of whether Qdrant happens to be running, not a meaningful
signal either way.

**docxtpl / python-pptx version notes:**
- `docxtpl==0.19.0` — exactly as pinned. Its `RichText` helper does not work in this environment
  (see bug #1 above); everything else used (plain `{{ var }}` substitution, `{% for %}` block
  loops spanning multiple paragraphs, inline `{% if %}/{% else %}/{% endif %}` within one
  paragraph) worked exactly as documented.
- `python-pptx==1.0.2` — exactly as pinned, no issues. `Presentation()`'s default template's
  layout index 1 is `"Title and Content"` (confirmed by name, not assumed by index) — matches
  the doc's instruction to use that one layout throughout.
- `python-docx` is installed at **1.2.0**, not the pinned **1.1.2** (pre-existing drift from an
  earlier session's environment setup, not something this session changed) — no observed
  behavioral difference for the API surface this layer uses (`Document`, `add_heading`,
  `add_paragraph`, `add_run`, `RGBColor`).
- `openpyxl==3.1.5` — exactly as pinned, no issues.

**Surprises a fresh session must know:**
- `tests/test_render.py` mutates `core.render.get_span` **at import time, unconditionally, for
  the lifetime of the process** — see the module's own docstring for why (the DoD script's bare
  `python -c` import has no pytest fixture machinery available). This means any *other* test
  file that imports `tests.test_render` (directly or via pytest's collection of the whole `tests/`
  directory) will also see `core.render.get_span` patched to the 4-span fixture KB, not the real
  `core.kb.get_span`. Harmless today (no other test file calls `core.render.render()`), but
  whoever builds L4's tests and wants to exercise a *real* end-to-end render against a live KB
  should do it in its own test run, not in the same pytest session as `tests/test_render.py`.
- The rendered `average_thickness` sample value (12.35 mm) does not equal the toy expression
  shown in `calculation` ("(12.4 + 10.5) / 2 = 11.45") — deliberate: `GroundedValue.value` is
  independent of the display text in `calculation` per the frozen schema, and the sample plan
  exists to exercise every code path, not to model a physically consistent inspection. L4's real
  plans should keep these consistent; this layer does not check that they are (no `eval()`, by
  design).

**Deviations from the doc (and why):** the two "design decisions beyond the doc's literal text"
above (deriving `source_note`/amber markers, deriving `calculations` from `plan.fields`) are
gap-filling, not contradictions — the doc's own DOCX template sketch already assumes a
`calculations`/`source_note` context that the frozen schemas don't literally carry, so someone
had to decide how to build it; done entirely within `core/render.py`, no other layer's files
touched. The `RichText`→`{% if %}` swap is a same-outcome substitution forced by an environment
bug, not a scope change.

### Open questions
- _(none new)_

### Next action
Session 8 — L4 Agent Orchestrator — start with `WorkbenchState` in `core/graph.py`.

## Session 8 — L4 Agent Orchestrator — 2026-09-07

**Status:** partial — `core/graph.py`/`core/prompts.py`/`tests/test_graph.py` are complete and
built exactly to the doc's six-node shape; all 7 non-integration tests pass for real. The three
`@pytest.mark.integration` tests and both `--demo` CLI commands were **not run to completion**
this session — every live attempt hit real, expensive, genuine LLM latency on this 8 GB M1
dev machine (not a bug being hidden: confirmed via repeated live observation, see below), and
the session was stopped partway through live verification at the user's explicit request due to
device heat during sustained local-model inference. What *is* verified live: every individual
node's LLM call path (PLAN, write-code, write-tests) was exercised directly, for real, multiple
times, in isolation — just not yet stitched into one recorded full-graph run.

**Files created/changed:** `core/graph.py`, `core/prompts.py`, `tests/test_graph.py` (all new,
per this layer's "Files You Own" list). `config.yaml`'s `sandbox.runtime` changed from `runsc`
to `runc` (see below — this session's fresh colima VM has no gVisor registered, same gap
Sessions 6/7 already noted; not an L4 file but needed for the CODING path's sandbox calls to
work at all here).

**Definition of Done — what actually ran:**

`pytest tests/test_graph.py -v -m "not integration"` → **PASS, for real**
```
collected 10 items / 3 deselected / 7 selected
tests/test_graph.py::test_graph_has_exactly_six_nodes PASSED
tests/test_graph.py::test_plan_capped_at_eight_steps PASSED
tests/test_graph.py::test_act_routes_back_to_act_until_cursor_exhausts_plan PASSED
tests/test_graph.py::test_verify_failure_routes_back_to_plan PASSED
tests/test_graph.py::test_iteration_budget_forces_escalation PASSED
tests/test_graph.py::test_trim_messages_bounds_context PASSED
tests/test_graph.py::test_state_is_checkpointed_and_resumable PASSED
7 passed, 3 deselected in 5.78s
```

`python -m core.graph --demo coding` and `--demo approval`, and
`pytest tests/test_graph.py -v -m integration` — **not completed**. Two live attempts were made
and killed partway through (once after ~24 minutes mid-second-test, once after ~15 minutes
mid-first-test) — not because anything crashed, but because (a) each attempt was taking far
longer than estimated on this hardware, sustaining the M1's CPU near 100% for the whole
duration and visibly heating the machine, and (b) the first attempt surfaced a real bug
(below) that needed fixing before a live run would even be worth completing. Given the choice
between burning another 20-40 minutes of sustained local inference to re-verify, or stopping to
document real findings honestly, the user chose to stop. **This is the same category of gap
Sessions 1-3 documented for GPU-dependent checks — a genuine dev-machine limitation, not a
skipped step** — except here the blocker is thermal/time on a fanless laptop rather than "no
GPU at all"; the real venue GPU box should make this a non-issue.

**Real bug found and fixed (via live, isolated diagnosis, not the full graph):** the first live
`--demo coding` attempt showed a structured-output call to `qwen2.5-coder:1.5b` fail validation
with `EOF while parsing a string` after ~15000 characters, and several subsequent calls each
took 100-150+ seconds (one hit 133.6s, another 149.2s) — a small local model running away into
unbounded generation instead of terminating. Rather than guess-and-reword the prompt, isolated
the exact cause with a sequence of minimal, cheap (1-3s each) repro scripts hitting Ollama
directly with the graph's real prompt constants and schemas:
- Ruled out `structured_output_mode: response_format` itself — `qwen2.5-coder:1.5b` honours it
  correctly and fast for both a trivial schema and a bare one-string-field schema.
- Ruled out `CLASSIFY_PROMPT` (the system message) as the sole cause — swapping it for a
  one-line placeholder did not fix a repro that included the word "test" in the task text.
- Isolated it to exactly this: **once the model sees any hint that tests/assertions are
  relevant to the current turn, `WRITE_CODE_PROMPT`'s old wording (no positive upper bound, only
  vague "keep it plain" instructions) let it try to cram type hints, docstrings, and even bare
  `assert` statements or ad-hoc test enumeration into the `code` field, and — being a very small
  quantized model — it doesn't reliably know when to stop, running past the token budget before
  the JSON closes.** Confirmed 3/3 reproducible failure with the original wording, 3/3 clean
  success after tightening it.
- **Fix:** `WRITE_CODE_PROMPT` now explicitly forbids type hints, docstrings, comments, and
  *assert statements*, and `WRITE_TESTS_PROMPT` now caps output at **"AT MOST 2 test functions
  or assert statements total"** — a concrete numeric bound, not a qualitative one. Verified 3/3
  clean on both the isolated minimal repro and the real `core.prompts.CLASSIFY_PROMPT` +
  `WRITE_CODE_PROMPT`/`WRITE_TESTS_PROMPT` + the full original task text (including the
  deliberately-self-contradictory "assert is_prime(1) is True even though it isn't" phrasing —
  that phrasing was *not* the problem, confirmed by testing it both ways).
- **Residual, honestly-reported limitation, not chased further:** even after the fix, the model
  sometimes still adds a stray `# comment` or a bare `assert` instead of a proper
  `def test_...():` wrapper — it doesn't perfectly obey every instruction. This doesn't block
  correctness (`pytest -q test_code.py` still exits nonzero on a bare failing assert at
  collection time, which `run_tests()`'s exit-code check still catches correctly), so it was
  left as a known small-local-model quirk rather than over-engineered away. **Prompt lesson for
  future sessions on this hardware class: give this specific model concrete numeric bounds
  ("at most N"), never vague qualitative ones ("keep it short") — the latter measurably does not
  work.**

**Design decisions and deviations from the doc's literal text:**
- **Checkpointer is `AsyncSqliteSaver`, not the sync `SqliteSaver` the doc names.** `core/graph.py`
  is async end to end (every node is `async def`, `run_task()`/`resume_task()` use `.ainvoke()`)
  per CLAUDE.md's own convention that `core/graph.py` is async — and the sync `SqliteSaver` in
  `langgraph-checkpoint-sqlite==2.0.1` raises `NotImplementedError` on every async method
  ("Consider using AsyncSqliteSaver instead" — the library's own error message). Confirmed via a
  direct experiment that LangGraph's sync `.invoke()` also does not support async node functions
  at all in this version (`TypeError: No synchronous function provided`), so there was no
  sync-everything alternative either. `AsyncSqliteSaver` is still a plain
  `SqliteSaver`-family checkpointer at `SETTINGS.paths.data / 'checkpoints.sqlite'` per the doc's
  intent, just the async-capable sibling. Built via a one-shot `asyncio.run()` at import time
  (since `GRAPH = build_graph()` must stay a plain synchronous module-level assignment) —
  confirmed this does *not* break correctness across later, separate event loops (pytest-asyncio
  spins a fresh loop per test; the CLI spins its own via `asyncio.run()` in `main()`) because
  `AsyncSqliteSaver`'s async methods only use `self.lock` (an `asyncio.Lock`, loop-agnostic since
  Python 3.10) and `self.conn` (an aiosqlite connection backed by its own thread, also
  loop-agnostic) — its `self.loop`-dependent code paths are only in the *sync* wrapper methods
  this project never calls.
- **A genuine, separately-diagnosed gotcha along the way: `import core.graph` alone hangs the
  process on exit for ~7 seconds** — aiosqlite's connection keeps a non-daemon background thread
  alive until explicitly closed, and neither Python's normal interpreter shutdown nor an
  `atexit`-registered close call actually runs before that thread would otherwise block exit
  (verified experimentally: an `atexit` handler registered right after import never even got a
  chance to print before the delay). It is a **bounded ~7s delay, not an infinite hang** — proven
  by polling process liveness every second rather than trusting a single `sleep N; check` snapshot,
  which is what produced the false "still hanging" read the first two times. Left as a documented
  characteristic rather than "fixed" further, since it costs a few seconds once per process, not
  per task.
- **The `PLAN` node is registered as `"plan_step"`, not `"plan"`.** LangGraph refuses
  `add_node("plan", ...)` when `"plan"` is also a state key (`ValueError: 'plan' is already being
  used as a state key`) — and `WorkbenchState.plan: list[PlanStep]` is required verbatim by the
  doc. Six nodes either way (`_NODE_NAMES` still has exactly 6 entries); this is a LangGraph API
  naming constraint, not a design change. `test_graph_has_exactly_six_nodes` checks against the
  actual registered names, not the string `"plan"` specifically.
- **`config.yaml`'s `sandbox.runtime`: `runsc` → `runc`.** This session's colima VM (freshly
  started, per the user's earlier "kill all" cleanup mid-session-6/7) has no gVisor registered —
  confirmed via `docker run --runtime=runsc hello-world` → `unknown or invalid runtime name`,
  `--runtime=runc` → works. `core/sandbox.py`'s own comment already names `runc` as "the
  documented fallback ONLY if runsc unavailable," so this is exactly that documented path, not
  an improvised workaround. Set back to `runsc` on the real venue box.
- **`ACT`'s cross-step data flow uses `PlanStep.payload["result"]`, not a 7th state field.**
  Neither `docs/L4_ORCHESTRATOR.md` nor the frozen `WorkbenchState` shape says how one step's
  LLM output (e.g. written code) reaches a *later* step (e.g. running that code) — `_find_prior_result()`
  scans already-executed steps for a payload key (`"code"`, `"tests"`, `"expression"`,
  `"findings"`, `"answer"`) written by an earlier step, kept entirely inside `core/graph.py`,
  no schema changes.
- **`VERIFY` re-derives mechanically from scratch rather than trusting ACT's cached result** —
  e.g. for CODING it calls `run_tests()` itself again (not just reading ACT's stored
  `SandboxResult`), for CALCULATION it reads the `verify_calculation()` result ACT already
  computed (that function is itself the independent-re-derivation check, so re-running it a
  second time would just repeat the same pure computation). This mirrors L7b's own
  "never trust, always re-validate" precedent from Session 7.
- **`EMIT` always passes `allow_review_spans=True` to `core.render.render()`.** By construction,
  `EMIT` is only ever reached after a human has approved at the `APPROVE` interrupt, and that
  interrupt's payload already surfaces `needs_review_spans` for the human to see — so an approval
  is, by definition, informed authorization to proceed past that flag. This is honouring the
  approval, not bypassing L7b's gate.

**Surprises a fresh session must know:**
- Local per-call latency on this machine is dominated by **routing, not the task itself** — every
  `route_and_complete()` call is actually *two* LLM calls (Arch-Router's selection, played by
  `gemma4-e2b`, then the chosen model's actual completion), and since the local Ollama profile
  has no true co-residency (PATCH_04, Session 2), alternating between `gemma4-e2b` and
  `qwen25-coder-1.5b` on every single step pays a model-reload cost nearly every time. Observed
  router-call latencies alone: 24.7s, 25.7s, 26.6s, 29.5s, 30.2s — before the actual task
  completion even starts. **A future session optimizing wall-clock time should look at whether
  the router step can be skipped when `RouteRequest.task_type` already implies an obvious model
  choice**, rather than touching L4's per-step logic further.
- Confirmed the checkpoint database resets are needed between demo attempts on the same
  `task_id` — `rm -f data/checkpoints.sqlite` was used before each live attempt in this session;
  a stale checkpoint for an already-completed or already-failed thread_id will resume from
  wherever it left off rather than starting fresh.
- `tests/test_graph.py`'s three `@pytest.mark.integration` tests exist and are believed correct
  (they mirror the same call patterns verified live in isolation), but have **never actually
  been run to a PASS/FAIL verdict** — do not report them as passing without running them for
  real first.

**Deviations from the doc (and why):** covered inline above (checkpointer class, node name,
config.yaml runtime). No node count, edge topology, verification mechanics, or context-trimming
behavior deviates from the doc's spec.

### Open questions
- **Live end-to-end verification of both demos and the three integration tests is still
  outstanding.** Whoever picks this up next should: `rm -f data/checkpoints.sqlite`, ensure
  colima + the `qdrant-l6` container + `ollama serve` are up, then run
  `pytest tests/test_graph.py -v -m integration` and both `python -m core.graph --demo coding` /
  `--demo approval` for real, ideally on a machine that won't overheat under 20-40 minutes of
  sustained local inference (or on the real venue GPU box, where this should be dramatically
  faster). Paste the real output into a new PROGRESS.md entry — do not mark L4 🟢 without it.

### Next action
Finish live verification of Session 8 (L4) before starting Session 9 — run
`pytest tests/test_graph.py -v -m integration`, `python -m core.graph --demo coding`, and
`python -m core.graph --demo approval` for real, then update PROGRESS.md with observed iteration
counts and wall-clock per task. Only after that: Session 9 — L8 Evidence & Audit Plane — start
with `policies/egress_observe.yaml`.

## Session 9 — L8 Evidence & Audit Plane — 2026-09-11

**Status:** partial — `core/receipt.py`, both Tetragon policy files, `scripts/verify_receipt.py`,
and `scripts/negative_control.sh` are all built exactly to the doc's required API/shape, and all
32 non-integration tests pass for real (no mocks — real Ed25519 signing/verification, real
canonical-JSON hashing, real synthetic log files). The two CLI-level DoD commands could not run
on this dev machine, for reasons outside this layer's files (see below) — not because anything
in L8 itself is broken. **A real, live R1 violation was also found and confirmed this session**
while diagnosing why a full-repo test run behaved strangely — see the Open Questions entry above,
this is the headline finding of the session, not a footnote.

**Files created/changed:** `core/receipt.py`, `policies/egress_observe.yaml`,
`policies/egress_enforce.yaml`, `scripts/verify_receipt.py`, `scripts/negative_control.sh`,
`tests/test_receipt.py` (all new, per this layer's "Files You Own" list — no other layer's files
touched). `data/workspaces/*` (stray leftover test artifacts from Session 8) deleted as pure
runtime-state hygiene, not a source-file change.

**Session start:** per the user's instruction, L4's still-pending live end-to-end verification
(Session 8's own "Next action") was explicitly deferred rather than run first — the user said
"let us save the test for last, go ahead with the next natural step," so this session proceeded
directly to L8 without re-attempting the thermally-expensive L4 demos.

**The dual egress-source design (this is the deviation to understand before reading anything
else in this entry):** `docs/L8_AUDIT.md` assumes Tetragon unconditionally (`TETRAGON_LOG`,
kprobe JSONL). This dev machine has no Tetragon (no eBPF on macOS) — the same category of gap
Session 1 documented for `nft`. Rather than build strictly to the doc and leave the whole layer
unverifiable here (the L0/L1 pattern for genuinely impossible platform gaps), this session
noticed `core/config.py` already had `AuditCfg.egress_source: Literal["pktap", "tetragon"]`
(added preemptively in PATCH_02, Session 2, with the comment "macOS dev; 'tetragon' on the Linux
demo box") and built `read_egress()` to dispatch on it:
- `"tetragon"` — parses Tetragon's real JSON export shape (`process_kprobe`/`tcp_connect`
  events, `args[].sock_arg.daddr`/`dport`, `KPROBE_ACTION_SIGKILL` for blocked). This is the
  doc's literal spec, for the real venue box.
- `"pktap"` — this dev machine's substitute log shape, defined by this session (not previously
  specified anywhere): one JSON object per line with EXACTLY `EgressEvent`'s own field names
  (`timestamp`, `binary`, `pid`, `destination_ip`, `destination_port`, `action`). **No producer
  for this log exists in the repo** — that is deliberately out of L8's file scope (a capture
  process is an L0 concern, the thing that starts/owns background services, same as the
  tetragon container itself). `read_egress()`/`build_receipt()`/`verify()` are written and
  fully tested against this log shape via synthetic fixtures, so they need no further change
  once a future L0 session adds a real pktap-tailing capture script. Recorded as an Open
  Question above, not implemented — building it would mean either exceeding this layer's file
  scope or improvising root-requiring `tcpdump` invocations without the user's explicit sign-off,
  neither of which this session did.
- Both paths converge on the same fail-closed rule (missing/empty log raises) and the same
  `list[EgressEvent]` — `build_receipt()`/`verify()` have zero awareness of which source is active.

**A real bug found and fixed before any test ran:** the first draft of `_canonical_payload()`
serialized datetimes via a hand-written `default=lambda obj: obj.isoformat()` fallback in
`json.dumps()`. `build_receipt()` passes raw Python `datetime` objects into this function, but
`verify()` passes `receipt.model_dump(mode="json")` — a dict where datetimes are **already**
strings, because pydantic serialized them first. Tested empirically:
`datetime.now(timezone.utc).isoformat()` produces `"...013695+00:00"`, while pydantic's
`model_dump(mode="json")` for the identical instant produces `"...013695Z"` — **different
strings for the same instant.** Since `_canonical_payload()` is supposed to produce
byte-identical output from both call sites (that is the entire point of a payload hash), this
would have made **every single receipt fail its own signature verification**, always, silently,
the first time anyone actually called `verify()` — caught before writing a single test, by
reasoning through the two call sites' actual input shapes rather than assuming symmetry. **Fix:**
introduced `_ReceiptPayload(BaseModel)`, a small pydantic model holding exactly the 9
payload fields (everything in `TaskReceipt` except `payload_sha256`/`signature_ed25519`/
`public_key_ed25519`, which are computed FROM this payload and would be circular to include).
`_canonical_payload()` now ALWAYS constructs `_ReceiptPayload(**receipt_fields)` and dumps
`.model_dump(mode="json")` of that — routing both call sites through the identical pydantic
serializer every time, regardless of whether the caller handed it raw objects or already-JSON
dicts (pydantic re-validates dicts into nested models transparently, e.g.
`route_decisions: list[RouteDecision]` accepts a list of plain dicts fine). Verified via
`test_sign_then_verify_roundtrip`, `test_receipt_json_is_stable_across_runs`, and by hand before
writing those tests.

**A second real (test) bug found while writing `test_tampered_artifact_hash_fails`:** the test
originally placed its throwaway artifact file at an arbitrary `tmp_path`, wrote a tampered
version, and asserted `verify()` would catch the mismatch — but it silently didn't
(`assert True is False` — i.e. `ok2` came back `True`). Root cause: `verify()`'s artifact-hash
check only looks at `SETTINGS.paths.outputs / receipt.task_id / filename` and
`SETTINGS.paths.outputs / filename` (matching exactly where `core.render.render()` actually
writes files, per Session 7 — `artifact_hashes` in the frozen `TaskReceipt` schema stores only a
bare filename, no path, so SOME convention is unavoidable). The test's artifact wasn't at either
location, so `verify()` correctly treated it as "not present on this machine" (not itself a
failure — a receipt should still verify on a machine that doesn't have the original files) and
skipped the check entirely — this is `verify()` behaving exactly as designed, and the test was
unrealistic. Fixed by monkeypatching `SETTINGS.paths.outputs` to the test's own `tmp_path` and
placing the artifact at the real convention's path before tampering it.

**Definition of Done — what actually ran, and what could not:**

`pytest tests/test_receipt.py -v -m "not integration"` → **PASS, for real**
```
collected 34 items / 2 deselected / 32 selected
tests/test_receipt.py::test_is_external_table[...] PASSED  (22 parametrized cases)
tests/test_receipt.py::test_canonical_payload_is_deterministic PASSED
tests/test_receipt.py::test_missing_tetragon_log_raises PASSED
tests/test_receipt.py::test_missing_tetragon_log_raises_even_when_empty PASSED
tests/test_receipt.py::test_read_egress_filters_by_time_window PASSED
tests/test_receipt.py::test_sign_then_verify_roundtrip PASSED
tests/test_receipt.py::test_external_event_sets_count_and_fails_verify PASSED
tests/test_receipt.py::test_tampered_field_fails_verification PASSED
tests/test_receipt.py::test_tampered_artifact_hash_fails PASSED
tests/test_receipt.py::test_receipt_json_is_stable_across_runs PASSED
tests/test_receipt.py::test_write_receipt_roundtrips_through_json PASSED
32 passed, 2 deselected in 0.65s
```
(2 more tests than the doc's 8 non-integration items — `test_missing_tetragon_log_raises_even_when_empty`
and `test_read_egress_filters_by_time_window` — added because the doc's own text calls out both
"missing" and "empty" as distinct failure cases, and time-window filtering is real logic in
`read_egress()` that the doc's own test list didn't otherwise cover.)

`python -m core.graph --demo doc_qa` → **could not run.** `core/graph.py`'s CLI (built Session 8)
only accepts `--demo coding`/`--demo approval` — `doc_qa` is not a registered choice. This is an
L4 gap, not an L8 one; recorded in Open Questions above rather than patched here.

`python scripts/verify_receipt.py "$(ls -t data/receipts/*.json | head -1)"` → **PASS, for real**,
using a synthetic clean receipt (real Ed25519 key generated at `data/signing_key.pem`, real
sign+verify, real canonical-JSON hash match):
```
Receipt        t-test-clean
Payload hash   MATCHES
Signature      VALID (ed25519, key 7eb0b455…)
Models used    gemma4-e2b (sha 614e2730…)
Tool calls     1  (all recorded)
Egress events  1 observed — 1 internal, 0 external
Artifacts      (none)
VERDICT        ✅ SOVEREIGN — no external connection during this task
```
Exit code 0, confirmed. Also confirmed the script's failure paths for real: a tampered
`route_decisions[0].reason` produces `Payload hash MISMATCH` + `Signature INVALID` +
`VERDICT ❌ NOT SOVEREIGN`, exit code 1; a missing file exits 2 with a usage-independent error;
no arguments prints usage and exits 2.

`bash scripts/negative_control.sh` → **could not run.** Needs a live `tetragon` Docker container
(`docker cp policies/egress_enforce.yaml tetragon:/etc/tetragon/tetragon.tp.d/`) — no such
container exists on this dev machine (colima/Docker were stopped per the user's request at the
end of Session 8, and even running, `docker-compose.yml`'s tetragon service has never been
started on macOS in this project — same category of gap as every prior session's Tetragon note,
compounded here by `--demo doc_qa` not existing either). The script is written faithfully to the
doc's literal steps (plus one added safety step — see Deviations below) for when a real Linux
Tetragon setup is available.

**Deviations from the doc (and why):**
- The dual `"tetragon"`/`"pktap"` egress source (covered in full above) — the single largest
  deviation, forced by this dev machine having no eBPF, using an escape hatch (`AuditCfg`)
  Session 2 already anticipated for exactly this problem.
- `scripts/negative_control.sh` has an added step 6, restoring `egress_observe.yaml` after the
  demo — the doc's own literal script only has 5 steps and never restores observe-only mode.
  Added because both this file's own header comment and `policies/egress_enforce.yaml`'s header
  comment already state enforcement must never be left loaded outside the demo; leaving the
  script itself unable to restore that state would contradict its own documented intent.
- `_ReceiptPayload` (an internal pydantic model, not in the doc's required API list) exists
  solely to fix the datetime-serialization bug above — an implementation detail behind
  `_canonical_payload()`'s unchanged signature, not a new public surface.

**Surprises a fresh session must know:**
- **The R1 network-leak finding (see Open Questions) is the load-bearing discovery of this
  session — read it before touching L3, L0, or `pytest.ini`.** It was found by accident (a
  seemingly-hung `pytest -q` run with flat CPU usage turned out to have an `ESTABLISHED` HTTPS
  socket via `lsof -p <pid>`), not by looking for it — worth remembering that "the test run is
  just slow" is not always the right explanation for an unexplained stall in this project.
- Cleaning `data/workspaces/*` before running the full suite is necessary on this machine right
  now (stray `test_code.py` from Session 8's live sandbox runs breaks pytest collection
  entirely) — this will recur after any future live CODING-task run until `pytest.ini` gets a
  `testpaths`/`norecursedirs` restriction (see Open Questions).
- `data/signing_key.pem` is generated on first `sign()` call, exactly per spec, mode 0600,
  already covered by `.gitignore`'s `*.pem` rule (added in PATCH_01, verified still present).
  Deleted the one generated during this session's manual testing before finishing, so the repo
  carries no signing key — whoever runs this for real will get a fresh one generated
  automatically on first use, as designed.
- Whole-repo regression with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` set (workaround for the
  R1 finding, NOT committed anywhere): `106 passed, 9 failed, 19 deselected` — all 9 failures
  are the pre-existing, already-documented `test_sandbox.py` Docker-daemon-unavailable gap
  (colima stopped, per the user's end-of-Session-8 cleanup request), unrelated to L8.

### Open questions
- See the two new entries added above this session's line (network-leak finding, `pytest.ini`
  collection hygiene, and the `--demo doc_qa` gap) — all three need action from a session other
  than L8's before this layer's remaining DoD commands can run for real.

### Next action
Whoever picks this up next should, in order: (1) fix the `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`
gap (L3/L0 territory) since it is a live, currently-reproducible air-gap violation, not a
documentation nit; (2) add a `doc_qa` demo path to `core/graph.py`'s CLI (L4) so
`scripts/negative_control.sh` can run as written; (3) then, on a machine with real Docker +
Tetragon (or the venue Linux box), run `bash scripts/negative_control.sh` for real and paste its
output here. Only after L8's own CLI-level DoD is genuinely green: Session 10 — L7 UI —
start with `api.py` (FastAPI, thin) per `docs/L7_UI.md`.

## Session 9 (continued) — closing the two L4 cross-layer gaps, live Tetragon verification — 2026-09-11

**Status:** the two cross-layer gaps identified above are now closed with the user's explicit
sign-off, and a REAL Tetragon container was stood up via colima and used to verify the whole
receipt pipeline end to end — including live kernel-level observation AND enforcement (a real
SIGKILL). One severe, previously-unknown LangGraph bug was found and fixed along the way that
would have crashed **every single task**, of any type, at the APPROVE step, on resume. Two real
bugs in the original `scripts/negative_control.sh` design were also found and fixed. L8's DoD is
now fully green for everything achievable on this dev machine; only one continuous,
unbroken run of `negative_control.sh` end-to-end (as opposed to its steps individually, all
independently verified) remains outstanding, due to this 8GB machine's resource limits under
simultaneous colima+Tetragon+Qdrant+Ollama load — not a code defect.

**User-approved cross-layer changes to `core/graph.py` (L4's file, not L8's):** per CLAUDE.md's
"raise it, don't implement" rule, the two gaps below were raised as an explicit question to the
user first; they said yes, implement it. Both are small and additive:
- Added a `doc_qa` demo path (`_demo_doc_qa()`, `_DEMOS` dict, `choices=sorted(_DEMOS)` on the
  CLI) — a plain question against the KB, verified purely mechanically per
  `_verify_doc_qa()`'s existing rule (every cited span id must resolve via `span_exists()`).
- Wired `node_emit()` to actually call `core.receipt.build_receipt()` / `write_receipt()` — this
  did not exist at all before this session (`node_emit` was built in Session 8, one session
  before L8 existed, so it structurally could not have called something that didn't exist yet).
  Per `docs/L8_AUDIT.md`'s own text — *"L4's node_emit calls build_receipt() then
  write_receipt(). That is the only coupling."* — this wiring is explicitly L4's job. The call
  is wrapped in `try/except WorkbenchError`, logging and continuing rather than failing the task,
  per the Drift tripwire "Letting L8 ... block a task" — a missing/dead monitor must never turn
  an otherwise-successful, human-approved task into a failure.

**A severe, independently-discovered LangGraph 0.2.60 bug, found and fixed (this is the most
important finding of this continuation):** the very first live `--demo doc_qa` run crashed with
`KeyError: 'render_plan'` inside `node_approve`, on resume, after a real 3-iteration
escalation. Diagnosed properly, not papered over blind:
- Built a minimal repro (plain `TypedDict`, 3-node linear chain, interrupt + resume) — state
  was preserved correctly. Ruled out.
- Built a second repro replicating the real `verify -> plan | approve` conditional-edge loop
  shape — state was STILL preserved correctly. Ruled out.
- Built a third repro using the REAL `WorkbenchState`/`PlanStep` pydantic types, with the plan
  step mutated in place exactly like the real `node_act`/`node_plan` do — **this one reproduced
  the exact crash**, cleanly and repeatably.
- **Root cause, confirmed empirically:** any `WorkbenchState` channel whose value was set only by
  the very first input (`_initial_state()`) and never rewritten by any node along the path taken
  disappears entirely (not just `None` — a genuine missing dict key) from the state handed to a
  node that gets REPLAYED after `interrupt()`/`resume()` in this LangGraph version. `render_plan`
  hits this for every CODING/DOC_QA task (no RENDER step ever runs); `artifacts` and `tool_trace`
  are equally exposed for any task that never touches EMIT-time artifacts or EXECUTE_CODE before
  reaching APPROVE. This is **not task-type-specific** — it would eventually crash coding and
  approval-note tasks too, on whichever fields they happen not to touch before their own resume.
  **This bug would have made every task that reaches the human-approval gate — i.e. every task,
  since APPROVE is un-skippable in the six-node graph — crash on resume**, before this fix.
- **Fix:** `node_approve` and `node_emit` now use `state.get(field, default)` throughout instead
  of `state[field]`, with defaults matching `_initial_state()`'s own (`[]` for lists, `None` for
  optionals). `task_spec`/`task_id` are still read via `.get()` for consistency, but a genuinely
  missing `task_spec` is treated as "cannot build a receipt, log and move on" rather than given a
  fake fallback that could produce a wrong receipt.
- **Verified fixed** by re-running the exact same live `--demo doc_qa` scenario twice more:
  both times the escalation-then-resume cycle completed cleanly, `status: done`, a receipt
  written to disk, `scripts/verify_receipt.py` returning `✅ SOVEREIGN`, exit 0.
- All three debug repro scripts were throwaway, not committed — the fix and this write-up are
  the retained artifacts.

**Real, live Tetragon verification — a genuine kernel-level eBPF capture, standing up colima +
a real container, per the user's explicit choice to attempt it:**
- `colima ssh -- uname -r` → `6.8.0-117-generic`; `/sys/kernel/btf/vmlinux` present (real BTF
  data, ~6.9 MB) — confirmed BEFORE attempting anything, rather than assuming it would work.
- Ran the real `quay.io/cilium/tetragon:v1.1.2` image with `--pid=host --cgroupns=host
  --privileged`, `policies/egress_observe.yaml` mounted, exactly matching `docker-compose.yml`'s
  intended shape. **It loaded and started tracking `tcp_connect` for real** (confirmed via
  `docker logs`: "Loaded generic kprobe program... -> tcp_connect", "Listening for events...").
- **Observation, proven live:** a native macOS `curl` to `https://example.com` produced **zero**
  Tetragon events (69 before, 69 after — confirmed by exact count, not just "looked empty").
  A `docker run --rm curlimages/curl ...` to the same URL, from a container running under the
  SAME colima Docker, was captured as a real `process_kprobe`/`tcp_connect` event with the
  correct `binary=/usr/bin/curl`, real `daddr` (Cloudflare's `104.20.23.154`), `dport=443`.
  **This is the single most load-bearing finding of this session for interpreting any
  Tetragon-sourced receipt on THIS dev machine: Tetragon here can only see traffic that
  originates inside colima's own Docker — never macOS-native process traffic (Ollama, this
  project's own Python processes).** This is a property of running Tetragon inside a
  Lima/colima Linux VM specifically, not a flaw in the L8 design — on the real bare-metal Linux
  venue box, `pid: host`/`cgroup: host` genuinely covers the WHOLE machine, no VM boundary
  exists, and this limitation does not apply.
- **Enforcement, proven live, twice:** first via a `docker cp`-based attempt that correctly
  demonstrated bug #1 below; then, after fixing the loading mechanism, `docker run --rm
  curlimages/curl:latest -m 5 -s -o /dev/null https://example.com` against the same URL
  returned **exit code 137 (SIGKILL)**, and the Tetragon log recorded the full causal chain for
  that exact process: a `process_kprobe`/`tcp_connect` event with
  `"action":"KPROBE_ACTION_SIGKILL"`, `"policy_name":"egress-enforce"`, immediately followed by
  a `process_exit` event with `"signal":"SIGKILL"` for the same `exec_id`. This is real,
  independently-verifiable, kernel-level enforcement — not simulated.

**Two real, previously-unknown bugs found in the ORIGINAL `docs/L8_AUDIT.md`/
`scripts/negative_control.sh` design itself (not introduced by an earlier session — found by
actually trying to run the documented mechanism against a real container):**
1. `docker cp policies/egress_enforce.yaml tetragon:/etc/tetragon/tetragon.tp.d/` **fails
   outright**: `Error response from daemon: mounted volume is marked read-only`. The
   `docker-compose.yml` volume (`./policies:/etc/tetragon/tetragon.tp.d:ro`) is correctly `:ro`
   for a real reason (a compromised container must not be able to rewrite its own security
   policy) — but that directly contradicts the negative-control script's own documented
   mechanism for loading enforcement. This is not colima/macOS-specific; it would fail
   identically on the real venue Linux box with the same compose file.
2. Even granting write access to the mount, **Tetragon v1.1.2 does not hot-reload
   `tetragon.tp.d` on a new file appearing there** — confirmed by copying the file in
   successfully and then testing: a curl through the policy succeeded (not killed) because
   `docker logs` showed only the original startup-time "Added TracingPolicy" messages, nothing
   new. The real, supported mechanism is Tetragon's own client, **`tetra tracingpolicy add
   <path>`** (and `tetra tracingpolicy delete <name>` to remove it), talking live to the running
   daemon's gRPC API — confirmed working via `docker exec tetragon tetra tracingpolicy add ...`
   immediately taking effect.
- **Fix applied to `scripts/negative_control.sh`:** step 1 now uses `docker exec tetragon tetra
  tracingpolicy add ...` instead of `docker cp`; step 6 (restore) uses `tetra tracingpolicy
  delete egress-enforce` instead of `docker cp`-ing the observe file back over it (deleting the
  enforce policy is sufficient — observe was never removed, since only ONE extra policy was
  ever added on top of it, not the whole directory replaced).
- **Also added, as a dev-machine-only, opt-in substitution (`NEGATIVE_CONTROL_IN_CONTAINER=1`
  env var, default off):** step 3's outbound-connection attempt uses a container-based curl
  instead of a native one, for the reason in the observation finding above — a native curl on
  this specific dev-machine setup would silently succeed and make the demo look broken even
  though enforcement is genuinely live. Left OFF by default so the script still matches the
  doc's literal, correct-for-bare-metal-Linux design unless a dev machine explicitly opts in.

**Definition of Done — updated status:**
- `pytest tests/test_receipt.py -v -m "not integration"` → 32/32 pass (unchanged, re-confirmed
  fresh after all `core/graph.py` changes above).
- `pytest tests/test_graph.py -v -m "not integration"` → 7/7 pass, re-confirmed fresh.
- `python -m core.graph --demo doc_qa` → **now runs successfully end to end**, real 6-node
  escalation-and-resume cycle, real receipt written. Ran successfully 3 separate times this
  continuation (once standalone confirming the resume-crash fix, twice more as part of
  `negative_control.sh` attempts).
- `python scripts/verify_receipt.py "$(ls -t data/receipts/*.json | head -1)"` → **exit 0,
  real output, pasted below.**
  ```
  Receipt        t-20260911-933e32
  Payload hash   MATCHES
  Signature      VALID (ed25519, key 77e3ba5a…)
  Models used    gemma4-e2b (sha 614e2730…)
  Tool calls     0  (all recorded)
  Egress events  0 observed — 0 internal, 0 external
  Artifacts      (none)
  VERDICT        ✅ SOVEREIGN — no external connection during this task
  ```
  This receipt's own `started_at`/`finished_at` (`16:22:25Z` → `16:24:53Z`, 148s, matching the
  established ~141-148s baseline for this task) confirm the underlying task genuinely completed
  quickly and cleanly — **while Tetragon's enforcement policy was loaded**, proving enforcement
  does not disrupt an unrelated normal task, exactly as the demo intends. `egress_events: []` is
  an honest, correct result given the container-only-visibility limitation above — this specific
  task's real traffic (Ollama, Qdrant) is genuinely invisible to this dev-machine's Tetragon
  instance, not hidden or faked as clean.
- `bash scripts/negative_control.sh` — **each individual mechanism it exercises is independently,
  completely proven live this session** (enforcement loading via `tetra`, a normal task
  completing under enforcement, a container connection being genuinely SIGKILL'd, the receipt
  verifying clean, restoring observe-only) — but **one single, unbroken run of the whole script
  start-to-finish was not achieved**. Two live attempts stalled for many minutes at the same
  point (after DOC_QA's evidence-retrieval step, before its answer-generation completes) under
  severe, confirmed memory pressure (`vm_stat` showed ~64 MB free RAM on this 8 GB machine with
  colima+Tetragon+Qdrant+Ollama all resident simultaneously) — **not a deadlock**: the second
  stalled attempt's own receipt (`t-20260911-933e32`, pasted above) proves the task actually
  finished internally in the normal ~148s and even wrote its receipt to disk correctly; the
  remaining "stall" was the same aiosqlite-trailing-thread-on-exit issue Session 8 first noted,
  except lasting many minutes under this session's heavier resource contention rather than the
  ~7-30s Session 8 observed — this delays the *shell script's* forward progress (bash blocks on
  its child), not the underlying task logic. Stopped here at the user's explicit direction
  rather than continuing to push an 8 GB machine already under confirmed severe memory pressure.

**Surprises a fresh session must know:**
- **The aiosqlite-trailing-thread-on-process-exit issue (Session 8) can last MUCH longer than
  "~7-30s" under real memory pressure** — one process in this session took 10+ minutes to fully
  exit after printing its final output and writing its receipt, with zero further work to do.
  A future session should treat "the python process for `--demo X` is still alive" as
  potentially meaningless once its expected final log output (or, more reliably, its receipt
  file on disk) has already appeared — check the RECEIPT's own `finished_at` timestamp before
  assuming a stall.
- **Never run two `core.graph --demo ...` invocations against the same `data/checkpoints.sqlite`
  concurrently.** One genuine hang this session was caused by exactly that (an old,
  slow-to-exit process from a previous invocation still holding the same sqlite file open when
  a new one started) — always confirm `ps aux | grep core.graph` is empty before starting a new
  run, not just that your own last command "should have" finished.
- `docker run --rm curlimages/curl:latest` needed a one-time image pull (`Pulling from
  cilium/tetragon`... `curl/8.7.1` base) this session — harmless, a small one-off download of a
  public test image for the negative-control substitute, not a project dependency.
- `config.yaml`'s `audit.egress_source` was temporarily flipped to `tetragon` for this session's
  live verification and has been reverted to `pktap` before finishing — see the file's own
  updated comment for why `pktap` remains the correct default here despite Tetragon genuinely
  working, and re-read it before ever "fixing" this back to `tetragon` without understanding
  the container-visibility caveat first.

**Deviations from the doc (and why):** all covered inline above (the two `core/graph.py`
changes, the `negative_control.sh` loading-mechanism fix, the opt-in container-curl
substitution). No change to any L8-owned file's public API/signatures.

### Open questions
- **One continuous, unbroken `bash scripts/negative_control.sh` run remains unverified**, purely
  due to this dev machine's resource limits under simultaneous colima+Tetragon+Qdrant+Ollama
  load — not a known defect. Whoever has access to a machine with more headroom (or the real
  venue box) should simply re-run it; every individual mechanism it depends on is independently
  proven working in this entry.
- The original two blockers' broader context (from before this continuation) — `HF_HUB_OFFLINE`
  not set anywhere in this repo's dev/test environment, and `pytest.ini` lacking
  `testpaths`/`norecursedirs` — are UNCHANGED by this continuation and still need a session with
  L3/L0/CONTRACTS scope to close.

### Next action
Session 10 — L7 Workbench UI + API — start with `api.py` endpoints, per `docs/L7_UI.md`. (L8's
own Definition of Done is now green for everything achievable on this dev machine; the one
remaining continuous negative-control run is an infra/resource-limit gap, not a code blocker,
and does not need to hold up starting L7.)

## Session 9 (continued again) — finishing the last two integration tests, a real policy bug fixed — 2026-09-11

**Status:** complete. `tests/test_receipt.py`'s two `@pytest.mark.integration` tests
(`test_live_capture_sees_internal_connections`, `test_negative_control_produces_external_event`)
had been written earlier this session but never actually executed. Ran them for real this
continuation — both failed on the first attempt, for a genuine reason, not a test-environment
fluke — diagnosed and fixed properly. **All 34 tests in `tests/test_receipt.py` now pass for
real** (32 non-integration + 2 integration), completing this layer's test suite in full.

**A real, previously-unnoticed bug found in `docs/L8_AUDIT.md`'s own literal policy YAML,
found and fixed:** `policies/egress_observe.yaml`'s kprobe selector used
`operator: "NotDAddr"` against the RFC1918/loopback ranges — meaning, read correctly, "only
report this kprobe hit when the destination is **NOT** one of these internal ranges." This
policy, copied verbatim from the doc, **structurally cannot ever capture an internal
connection** — not "deprioritizes" it, excludes it at the eBPF level before Tetragon even
considers reporting it. Confirmed by direct experiment: a real, verified container-to-Qdrant
connection (via `host.docker.internal`, later confirmed to resolve through
`192.168.5.2 → sshd relay → docker-proxy → 172.17.0.2`, all genuinely RFC1918) produced **zero**
`process_kprobe` events under the original policy, and started appearing correctly the moment
the filter was removed. This directly contradicts `core/receipt.py`'s own design — the
`EgressEvent.is_external` field and the `is_external()` function exist specifically to classify
BOTH internal and external captured connections; a capture policy that only ever reports
external ones makes that classification function partially pointless and makes
`test_live_capture_sees_internal_connections` (also specified in the same doc) impossible to
ever pass, on any machine, including the real venue box — this is not a dev-machine artifact.
**Fix:** removed the `NotDAddr` selector from `policies/egress_observe.yaml` entirely — it now
captures every `tcp_connect`, internal and external alike, exactly as its own header comment
already claimed ("Observes every outbound TCP connect attempt") before this fix made it true.
`policies/egress_enforce.yaml` is **unchanged** — its `NotDAddr` filter is correct and
load-bearing there: enforcement must only ever kill genuinely external connections, never
internal Qdrant/sandbox traffic, or it would break the system it's supposed to protect.

**A second, smaller real bug found while building the fix for the tests themselves:** the
initial container-based "internal connection" substitute used `qdrant-l6` as a hostname
(`docker run curlimages/curl http://qdrant-l6:6333/...`) — this fails outright
(`http_code=000`) because Docker's default `bridge` network (which `qdrant-l6` runs on, having
been started with a plain `docker run` and no custom network) does **not** do name-based DNS
resolution between containers — only user-defined networks do. Fixed by using
`host.docker.internal` instead (colima's documented, working route from inside a container back
to the host's exposed port), confirmed working via a direct `curl` before relying on it in a test.

**Test design fix, entirely within L8's own file scope:** both integration tests now dispatch on
`SETTINGS.audit.egress_source` via two small helpers (`_trigger_internal_connection()`,
`_trigger_external_connection()`) — a native call for `"pktap"`, a container-based call for
`"tetragon"` — exactly the same fix already applied to `scripts/negative_control.sh`'s
`NEGATIVE_CONTROL_IN_CONTAINER` flag earlier this session, for the identical underlying reason
(a Tetragon-in-a-colima-VM setup cannot see native macOS process traffic at all).

**Definition of Done — final, complete state:**
```
pytest tests/test_receipt.py -v -m "not integration"  → 32 passed
pytest tests/test_receipt.py -v -m integration         → 2 passed
                                                          (test_live_capture_sees_internal_connections,
                                                           test_negative_control_produces_external_event)
pytest tests/test_receipt.py tests/test_graph.py -v -m "not integration" → 39 passed, 5 deselected
```
All real, no mocks, against a genuinely running colima + Tetragon (v1.1.2, real eBPF kprobes) +
Qdrant stack. `config.yaml`'s `audit.egress_source` reverted to `pktap` afterward (same reasoning
as the prior continuation entry — this Tetragon setup still only sees container-originated
traffic, `pktap` is the honest default until a real capture producer exists for native traffic).

**Surprises a fresh session must know:**
- **`policies/egress_observe.yaml` no longer has a destination filter at all — it will be
  noisier than before** (every internal chatter connection is now a logged event, not just
  external attempts). This is the correct, intended tradeoff per the design reasoning above; do
  not "fix" this back to a NotDAddr filter without re-reading this entry first — that exact
  change is what silently broke internal-connection observability in the first place.
- Two more stray, slow-to-exit `core.graph`/pytest processes were found and killed this
  continuation (one from over 40 minutes earlier in the session, per its start timestamp) — this
  reinforces the Session 9 (continued) finding that these can linger far longer than expected;
  always `ps aux | grep -E "core.graph|pytest.*test_graph"` and kill anything stale before
  starting a new run against `data/checkpoints.sqlite`.
- `docker run --rm curlimages/curl:latest` connecting to `host.docker.internal` resolves through
  a real multi-hop chain on this colima setup (`192.168.5.2` gateway → `sshd` port-forward relay
  → `docker-proxy` → the target container's actual bridge IP) — all of it real, all of it now
  correctly captured as separate internal `tcp_connect` events per hop. Useful to know if a
  future receipt's egress_events list looks surprisingly long for a single logical connection —
  that's multiple real relay hops, not duplicate/buggy logging.

**Deviations from the doc (and why):** the `egress_observe.yaml` fix is a deviation from the
doc's literal YAML — justified in full above; it makes the policy's own header comment and
`core/receipt.py`'s design intent actually true, where the literal original text was not just an
interpretation gap but a directly disprovable claim ("observes every outbound TCP connect
attempt") given what the NotDAddr selector actually did.

### Open questions
- _(none new this continuation)_

### Next action
Unchanged: Session 10 — L7 Workbench UI + API — start with `api.py` endpoints, per
`docs/L7_UI.md`. L8's test suite is now completely finished (34/34 across both marks); the one
remaining continuous `negative_control.sh` run stays a resource-limit gap, not a code blocker.

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
