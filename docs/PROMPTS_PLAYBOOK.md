# PROMPTS PLAYBOOK

How to drive Claude Code through this build without it reading the whole doc set every session.

---

## The token rule

Claude Code auto-loads `CLAUDE.md` (~1.5k tokens). Every session adds **exactly two more files**:
`docs/01_CONTRACTS.md` (~2.5k) and one layer doc (~2–3k). Total context cost per session:
**~7k tokens before any code**. Reading all ten layer docs would cost ~30k and cause drift, because
Claude Code will start "helpfully" building adjacent layers.

> **The single most important line in every prompt is the negative one:**
> `Do NOT read any other file in docs/.`

---

## Session order

| # | Session | Depends on | Est. |
|---|---------|-----------|------|
| 0 | CONTRACTS | — | 45 min |
| 1 | L0 Host | 0 | 90 min |
| 2 | L1 Serving | 0, 1 | 60 min |
| 3 | L2 Router | 2 | 60 min |
| 4 | L5 Sandbox | 0 | 75 min |
| 5 | L3 Ingestion | 2 | 90 min |
| 6 | L6 KB | 5 | 60 min |
| 7 | L7b Renderer | 6 | 90 min |
| 8 | L4 Orchestrator | 3,4,5,6,7 | 120 min |
| 9 | L8 Audit | 1, 8 | 75 min |
| 10 | L7 UI | 8, 9 | 120 min |
| 11 | Rehearsal | all | 60 min |

L5 (session 4) comes before L3/L6 deliberately: it depends only on L0, so if ingestion runs
long you still have R14 demoable.

---

## Session 0 — CONTRACTS

```
Read CLAUDE.md and docs/01_CONTRACTS.md. Do NOT read any other file in docs/.

Implement core/schemas.py and core/config.py EXACTLY as specified in 01_CONTRACTS.md.
Every class, every field, every default, same names, same order. Add the WorkbenchError
exception class. Add core/__init__.py.

Also write tests/test_schemas.py proving: EvidenceSpan rejects confidence > 1.0; Finding
rejects an empty evidence_refs list; ModelManifest round-trips through YAML; load_settings()
parses config.yaml into Settings.

Do not implement any layer logic. Do not import openai, docker, qdrant, or docling.

Definition of Done: `pytest tests/test_schemas.py -v` passes and
`python -c "from core.config import SETTINGS; print(SETTINGS)"` prints resolved absolute paths.

Then update PROGRESS.md per the template and stop.
```

---

## Sessions 1–10 — the template

Substitute the three bracketed values. Nothing else changes.

```
Read CLAUDE.md, docs/01_CONTRACTS.md, and docs/[LAYER_DOC]. Do NOT read any other file in docs/.

Also read PROGRESS.md for handoff notes from previous sessions.

Build [LAYER_NAME] exactly as its doc specifies. Create only the files listed under
"Files You Own". Import everything else from core/ and trust the contracts — do not open or
edit another layer's files.

Before you write code: state in one line what you are building and paste the Definition of Done
command you will run at the end.

Honour every item in the "Drift tripwires" section. If you believe a tripwire must be violated,
stop and write the argument into PROGRESS.md under "## Open questions" instead of implementing it.

Work through the doc's build order. Write the tests listed in the doc. Run the Definition of
Done command and paste its real output — do not claim success from reading the code.

Finish by updating PROGRESS.md with the session exit template, including the "## Next action" line.
```

Concrete fills:

| Session | `[LAYER_DOC]` | `[LAYER_NAME]` |
|---|---|---|
| 1 | `docs/L0_HOST.md` | L0 — Host Substrate |
| 2 | `docs/L1_SERVING.md` | L1 — Model Serving Plane |
| 3 | `docs/L2_ROUTER.md` | L2 — Router |
| 4 | `docs/L5_SANDBOX.md` | L5 — Tool & Sandbox Plane |
| 5 | `docs/L3_INGESTION.md` | L3 — Document Ingestion |
| 6 | `docs/L6_KB.md` | L6 — Knowledge Base |
| 7 | `docs/L7B_RENDERER.md` | L7b — Deliverable Renderer |
| 8 | `docs/L4_ORCHESTRATOR.md` | L4 — Agent Orchestrator |
| 9 | `docs/L8_AUDIT.md` | L8 — Evidence & Audit Plane |
| 10 | `docs/L7_UI.md` | L7 — Workbench UI + API |

---

## Mid-session prompts

**Before compacting** (use this the moment context feels tight, not after):
```
Stop adding code. Finish the function you are in the middle of, run the Definition of Done
command, and paste the output. Then update PROGRESS.md: what is complete, what is not, the
exact next function to write, and any surprise a fresh session would need to know.
Then compact.
```

**After compacting:**
```
Re-read CLAUDE.md, docs/[LAYER_DOC], and PROGRESS.md. Do NOT read any other file in docs/.
Resume from the "## Next action" line in PROGRESS.md. Do not restructure or refactor
anything already written — continue forward only.
```

**When it starts drifting** (building adjacent layers, adding unrequested features):
```
Stop. You are outside the mission lock for this layer. Re-read the MISSION LOCK and Drift
tripwires sections of docs/[LAYER_DOC]. List which of your last changes fall outside
"Files You Own", revert them, and continue with only what the doc specifies.
```

**When it's stuck on an external dependency:**
```
Do not work around this by changing the architecture. Write the exact error into PROGRESS.md
under "## Open questions", implement the documented fallback if the doc names one, and move to
the next item in the build order. We resolve blockers between sessions, not inside them.
```

**When it declares completion without proof:**
```
Paste the actual terminal output of the Definition of Done command from docs/[LAYER_DOC].
If you have not run it, run it now. A layer is not complete until that command exits 0.
```

**When a test won't pass:**
```
Do not delete, skip, or weaken the test to make the suite green. The test encodes a requirement.
Either fix the implementation, or if the test itself is wrong, explain why in PROGRESS.md
before changing it.
```

---

## Cross-layer repair prompt

Use when a later session discovers an earlier layer is genuinely wrong. Never let a session
freelance edits into another layer's files.

```
Read CLAUDE.md, docs/01_CONTRACTS.md, docs/[OWNING_LAYER_DOC]. Do NOT read any other file in docs/.

PROGRESS.md reports this defect in [OWNING_LAYER]: [paste the exact symptom and error].

Reproduce it, fix it inside that layer's owned files only, and add a regression test to
tests/test_[layer].py. Re-run that layer's Definition of Done and paste the output.
Do not change core/schemas.py. Do not touch any other layer.
```

---

## Session 11 — Rehearsal

```
Read CLAUDE.md and PROGRESS.md only. Do NOT read anything in docs/.

Run the full demo sequence and record wall-clock timing for each step:

  1. make preflight                              → all green, negative control fails correctly
  2. Task A (R12+R14): "Write a Python function that parses P&ID tag numbers like
     10\"-P-1502-A1A into components, with tests."
     → confirm router chose qwen25-coder-7b, tests ran in the gVisor sandbox, and at least
       one iteration occurred
  3. Task B (R13+R15): upload tests/fixtures/inspection_scanned.pdf,
     "Extract the key findings and draft an approval note for V-101."
     → confirm PaddleOCR-VL ran, SOP context was retrieved, calculations show steps,
       .docx downloads and opens, provenance appendix is populated
  4. Click three spans in the evidence panel → red bbox lands on the right region
  5. python scripts/verify_receipt.py <latest>   → ✅ SOVEREIGN, 0 external
  6. bash scripts/negative_control.sh            → curl visibly killed, real task unaffected
  7. POST /admin/reload_models with a fifth manifest → appears in routing with zero code change

Write the results into PROGRESS.md as "## Rehearsal N". For each failure, add a one-line fix
task with the owning layer named. Do not fix anything during the rehearsal — record and continue.
```

Run this three times. The first finds bugs, the second finds timing problems, the third is the
one you can perform.

---

## Anti-drift checklist (paste into any session that feels off-track)

```
Answer these seven, briefly:
1. Which layer am I building?
2. Which requirement IDs (R1–R16) does it serve?
3. Which files am I permitted to create or edit?
4. Have I edited any file outside that list? (If yes, revert.)
5. Have I added a dependency not in requirements.txt? (If yes, justify or remove.)
6. Have I violated any Drift tripwire in my layer doc?
7. What is my Definition of Done command, and has it exited 0?
```

---

## PROGRESS.md template

Every session appends this block. Never overwrite previous entries.

```markdown
## Session N — [LAYER] — YYYY-MM-DD

**Status:** complete | partial | blocked
**Files created/changed:** …
**Definition of Done:** command run → PASS/FAIL, with output pasted
**Surprises a fresh session must know:** …
**Deviations from the doc (and why):** …

### Open questions
- …

### Next action
[Exact next thing: session number, layer, and first function to write]
```
