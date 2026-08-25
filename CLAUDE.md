# CLAUDE.md — Project Constitution

> Claude Code loads this file automatically in every session. It is deliberately short.
> **Do not read other layer docs unless the session prompt names them.**

## What this project is

A **sovereign, air-gapped, on-premise agentic AI workbench** for confidential industrial work
(SIH 2026, PS 26117). It runs open-weight LLMs on the organisation's own GPU via vLLM,
auto-selects models per task, executes agentic multi-step work in a sandbox, reads scanned
engineering documents, and emits real Word/Excel/PowerPoint deliverables — while producing a
kernel-level cryptographic proof that nothing left the building.

## The 16 requirements (every line of code must trace to one)

| ID | Requirement |
|----|-------------|
| R1 | Air-gapped; nothing leaves premises |
| R2 | Multiple open-weight models served at once |
| R3 | **Automatic** model selection based on task needs |
| R4 | New models addable **without redesigning the system** |
| R5 | Agent plans multi-step work |
| R6 | Local tools: file r/w, code exec in sandbox, spreadsheet, doc search |
| R7 | Agent iterates, does not answer once and stop |
| R8 | Scanned PDFs, handwriting, engineering drawings, photos via on-device OCR/vision |
| R9 | Real deliverables: Word/Excel/PPT, working code, calculations with steps shown |
| R10 | Grounded in org's own manuals, SOPs, correspondence (local KB) |
| R11 | Runs on a single mid-range GPU workstation |
| R12 | DEMO: auto model selection across ≥2 task types |
| R13 | DEMO: scanned inspection report → findings → Word approval note |
| R14 | DEMO: coding task run **and verified** in sandbox |
| R15 | DEMO: multimodal / scanned document understanding |
| R16 | DEMO: prove zero external calls via logs / network monitor |

## Layer map (one session per layer)

| Layer | Name | Doc | Serves |
|-------|------|-----|--------|
| L0 | Host substrate | `docs/L0_HOST.md` | R1 |
| L1 | Model serving | `docs/L1_SERVING.md` | R2, R4, R11 |
| L2 | Router | `docs/L2_ROUTER.md` | R3, R4, R12 |
| L3 | Document ingestion | `docs/L3_INGESTION.md` | R8, R15 |
| L4 | Agent orchestrator | `docs/L4_ORCHESTRATOR.md` | R5, R7 |
| L5 | Tool & sandbox plane | `docs/L5_SANDBOX.md` | R6, R14 |
| L6 | Knowledge base | `docs/L6_KB.md` | R10 |
| L7b | Deliverable renderer | `docs/L7B_RENDERER.md` | R9, R13 |
| L7 | Workbench UI | `docs/L7_UI.md` | R11, R12, R13 |
| L8 | Evidence & audit | `docs/L8_AUDIT.md` | R1, R16 |

Shared type contracts live in `docs/01_CONTRACTS.md` and are implemented **once** in
`core/schemas.py`. Every layer imports from there. No layer redefines a shared type.

## Global non-negotiables

1. **No network egress, ever.** No `pip install` at runtime, no model downloads at runtime,
   no telemetry, no CDN fonts, no external API. All model weights are pre-staged on disk.
2. **The sandbox has no network interface.** `network_mode="none"`. Not a firewall rule.
3. **The LLM never writes binary office files.** It emits a schema-constrained `RenderPlan`;
   deterministic Python renders the file. See L7b.
4. **Every extracted value carries provenance.** `EvidenceSpan` with doc_id + page + bbox.
   A `RenderPlan` field without a resolvable `evidence_ref` is a hard validation error.
5. **Structured output uses vLLM's native `guided_json`.** Do not install Outlines,
   Instructor, or any other structured-output library.
6. **Adding a model = adding a YAML manifest.** If a task requires editing Python to add a
   model, the design is wrong (violates R4).
7. **Python 3.11. Type hints everywhere. Pydantic v2 for all cross-layer data.**

## Global forbidden list (drift tripwires)

Do **not** build, install, suggest, or scaffold any of the following. They are out of scope
and adding them is the primary failure mode of this project:

- Authentication, RBAC, SSO, multi-tenancy, user management
- Kubernetes, Helm, Cilium CNI, service mesh, autoscaling, HA
- LiteLLM, LangChain (LangGraph only), MCP, OpenAI Agents SDK, CrewAI, AutoGen
- Model fine-tuning, LoRA training, RLHF, distillation
- Cloud SDKs (boto3, azure-*, google-cloud-*) — these are an air-gap violation
- Prometheus/Grafana/OpenTelemetry stacks, log shippers
- Docker Compose orchestration beyond what `docs/L0_HOST.md` specifies
- Rewriting another layer's files "to make mine work" — raise it in `PROGRESS.md` instead
- Speculative "future-proofing", plugin systems, abstract base classes with one implementation

If you believe one of these is genuinely required, **stop and write the argument into
`PROGRESS.md` under `## Open questions`. Do not implement it.**

## Repo layout (authoritative — do not invent new top-level dirs)

```
sovereign-workbench/
├── CLAUDE.md                 # this file
├── PROGRESS.md               # session handoff log — ALWAYS update before ending
├── config.yaml               # single source of runtime config
├── requirements.txt
├── Makefile
├── docs/                     # layer specs (read only what your prompt names)
├── manifests/                # one YAML per model — the L1 registry
├── core/                     # all library code, one module per layer
│   ├── schemas.py            # L-shared contracts (owned by CONTRACTS session)
│   ├── config.py             # config loader (owned by CONTRACTS session)
│   ├── serving.py            # L1
│   ├── router.py             # L2
│   ├── ingest.py             # L3
│   ├── graph.py              # L4
│   ├── tools.py              # L5
│   ├── sandbox.py            # L5
│   ├── kb.py                 # L6
│   ├── render.py             # L7b
│   └── receipt.py            # L8
├── sandbox/Dockerfile        # L5
├── policies/                 # Tetragon policies — L8
├── templates/                # docxtpl / pptx templates — L7b
├── scripts/                  # host setup, model staging — L0
├── tests/                    # one test_<layer>.py per layer
├── api.py                    # FastAPI, thin — L7
└── ui.py                     # Streamlit — L7
```

## Session protocol (mandatory)

**At session start:** read `CLAUDE.md`, `PROGRESS.md`, `docs/01_CONTRACTS.md`, and your layer
doc. Nothing else. State in one line which layer you are building and its Definition of Done.

**During the session:** implement only files listed in your layer doc's `Files You Own`.
If you need something from another layer, import it from `core/` and trust the contract —
do not open that layer's doc or edit its files.

**Before ending or compacting:** update `PROGRESS.md` with the template at the bottom of that
file. A session that ends without updating `PROGRESS.md` has failed, regardless of code written.

**If context is running low:** finish the current function, run the verification command,
update `PROGRESS.md`, then compact. After compaction, re-read `CLAUDE.md` + your layer doc +
`PROGRESS.md` and continue from the `## Next action` line.

## Verification is not optional

Every layer doc ends with a **Definition of Done** containing a shell command. The layer is not
complete until that command exits 0. Do not report a layer as finished based on reading the code.
