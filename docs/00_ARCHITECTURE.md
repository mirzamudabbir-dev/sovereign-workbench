# 00_ARCHITECTURE — read once at kickoff, then never again

> This file is for **humans**, at project kickoff. Claude Code sessions should **not** read it —
> `CLAUDE.md` carries everything a session needs. It is here so the team shares one mental model.

## The claim

An air-gapped agentic AI workbench that runs open-weight models on the organisation's own GPU,
auto-selects the right model per task, executes multi-step work in a sandbox, reads scanned
engineering documents, produces real Word/Excel/PowerPoint deliverables with click-through
provenance, and emits a kernel-level cryptographic proof that nothing left the building.

## Layer map

```
┌──────────────────────────────────────────────────────────────────────┐
│  L8  EVIDENCE & AUDIT      Tetragon eBPF · Ed25519 task receipts     │ R1,R16
│      ─ observes every layer below, out-of-band, kernel-level ─       │
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│  L7  WORKBENCH UI          FastAPI + Streamlit · task-centric        │ R11,R12,R13
└──────────────────────────────┬───────────────────────────────────────┘
                               │ TaskSpec
┌──────────────────────────────▼───────────────────────────────────────┐
│  L4  ORCHESTRATOR          LangGraph · 6 nodes · bounded iteration   │ R5,R7
│      classify → plan → act → verify → approve → emit                 │
└──┬────────────┬─────────────┬──────────────┬─────────────────────────┘
   │RouteReq    │ToolCall     │Query         │RenderPlan
┌──▼─────────┐ ┌▼───────────┐ ┌▼───────────┐ ┌▼──────────────────────┐
│ L2 ROUTER  │ │ L5 SANDBOX │ │ L6 KB      │ │ L7b RENDERER          │
│ capability │ │ gVisor     │ │ Qdrant     │ │ docxtpl · python-pptx │
│ filter +   │ │ runsc      │ │ hybrid     │ │ openpyxl              │
│ Arch-Router│ │ no network │ │ BGE-M3+BM25│ │ fails closed          │
└──┬─────────┘ └────────────┘ └──▲─────────┘ └───────────────────────┘
   │model_id                     │EvidenceSpan     R3,R4,R12 / R6,R14 / R10 / R9,R13
┌──▼──────────────────────────────┴────────────────────────────────────┐
│  L1  MODEL SERVING         vLLM ×4 · manifests · guided_json         │ R2,R4,R11
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│  L3  INGESTION             Docling (native) · PaddleOCR-VL (scans)   │ R8,R15
└──────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│  L0  HOST                  nftables deny · gVisor · offline weights  │ R1
└──────────────────────────────────────────────────────────────────────┘
```

## Four ideas the whole design rests on

1. **The manifest is the seam.** A model is a YAML file. Adding one touches zero Python.
   That is R4, and `test_registry_reload_picks_up_new_file` is its executable proof.

2. **Filter before you prefer.** Modality, context length and grammar support are hard
   constraints, not preferences. Arch-Router chooses among the survivors — never among all models.

3. **Two planes: probabilistic planner, deterministic renderer.** The model emits a
   schema-constrained `RenderPlan`; Python writes the file. A hallucinated number becomes a
   validation error that fails closed, not a fluent sentence someone signs.

4. **Prove, don't assert.** The air gap is enforced at L0 and *proved* at L8, by independent
   mechanisms. A receipt generated from application logs would be circular; it comes from the kernel.

## Flagship demo path (R13, touches every layer)

Engineer drops a scanned inspection PDF → **L3** classifies as scan, PaddleOCR-VL emits spans
with bboxes → **L4** plans five steps → **L2** routes the drafting step to `qwen25-vl-7b`,
decision shown live *(R12)* → **L6** returns the applicable SOP clause (BM25 catches `V-101`,
dense catches "minimum thickness") → **L5** runs the remaining-life calculation with units and
re-derives it independently → **L4** emits a grammar-constrained `RenderPlan` → **L7b** resolves
every `evidence_ref` and renders `approval_note.docx` → **L7** shows click-through highlights,
engineer approves → **L8** emits a signed receipt with zero external egress *(R16)*.

## Deliberately cut

MCP · authentication/RBAC · Kubernetes · LiteLLM · vLLM Sleep Mode and model swapping ·
ColPali/visual retrieval · rerankers · P&ID symbol and graph extraction · fine-tuning ·
model ingestion security gate · Prometheus/Grafana · PDF export · multi-agent patterns.

Each was evaluated and each fails the same test: **no line in the PS requires it.** Several are
strong v2 features. None of them is worth a hackathon hour before the six demo requirements
are green.

## Team split

| Owner | Layers | Note |
|---|---|---|
| A | L0 + L8 | Systems-strongest person. L8 is the highest-scoring work in the project. |
| B | L1 + L2 | Smallest surface; finishes first, then helps D. |
| C | L3 + L6 | Heaviest ML lift; start early. |
| D | L5 + L4 | L4 is the sprawl risk — hold the six-node line. |
| E | L7b + L7 | **Build the renderer before the UI.** The UI is a view over `RenderPlan`. |

## Build order

`L0 → CONTRACTS → L1 → L2` *(R12 demoable)* `→ L5 → L4-stub` *(R14 demoable)*
`→ L3 → L6 → L7b` *(R13, R15 demoable)* `→ L4-full → L8 → L7` *(R16 demoable)*

You are demoable at four checkpoints. If time runs out, you still have something to show.
