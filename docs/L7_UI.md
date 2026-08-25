# L7 — WORKBENCH UI + API

## MISSION LOCK

**Build:** a thin FastAPI backend over `core.graph`, and a Streamlit workbench that makes the
four demo requirements visible on screen.

**You are NOT building:** a chat app. The primary object is a **task producing a deliverable
with provenance**, not a message thread. No conversation history, no personas, no streaming
token display.

**Serves:** R11, R12 (routing visible), R13 (approval note produced and approved), R15, R16
(receipt visible).

**Files You Own:**
```
api.py
ui.py
tests/test_api.py
```

---

## `api.py` — FastAPI, thin

```python
POST /tasks                 # multipart: instruction, task_type, files[] → {task_id}
GET  /tasks/{id}            # full WorkbenchState (JSON-safe)
POST /tasks/{id}/approve    # {approved: bool, note: str} → resumes the LangGraph interrupt
GET  /tasks/{id}/receipt    # TaskReceipt JSON
GET  /tasks/{id}/artifact/{name}   # FileResponse — the download
GET  /spans/{span_id}       # EvidenceSpan
GET  /spans/{span_id}/crop  # PNG crop of the bbox (core.ingest.crop_span)
GET  /models                # registry + health, for the status bar
GET  /health                # aggregate of vLLM ×4, Qdrant, Tetragon
POST /admin/reload_models   # REGISTRY.reload() — the live R4 demo
GET  /kb/stats
```

Rules: every handler is ≤20 lines and delegates to `core.*`. Uploads go to
`SETTINGS.paths.uploads`, never `/tmp`. Bind `127.0.0.1` only. No auth — deliberately out of
scope, single-workstation deployment. No CORS wildcard.

Run the graph as a background task; the UI polls `GET /tasks/{id}` every 2 s.

---

## `ui.py` — Streamlit, five panels

```
┌─────────────────────────────────────────────────────────────────────┐
│ SOVEREIGN WORKBENCH        🟢 4 models  🟢 KB 1,284 spans  🟢 Monitor│  ← status bar
├──────────────────────┬──────────────────────────────────────────────┤
│ NEW TASK             │  ROUTING          ← R12                      │
│  [instruction]       │  ┌────────────────────────────────────────┐  │
│  [task type ▾]       │  │ Step s3 · needs image · 4,102 tokens    │  │
│  [drop files]        │  │ ✅ qwen25-vl-7b    "reads images and…"  │  │
│  [ Run ]             │  │ ❌ qwen25-coder-7b  no image modality   │  │
│                      │  │ ❌ arch-router      reserved for routing │  │
│ PLAN                 │  └────────────────────────────────────────┘  │
│  1 ✅ INGEST         ├──────────────────────────────────────────────┤
│  2 ✅ RETRIEVE       │  DELIVERABLE      ← R13                      │
│  3 ⏳ LLM_CALL       │  Draft approval note                         │
│  4 ⬜ EXECUTE_CODE   │  Shell thickness  11.8 mm  [insp-2214#p7.b1] │
│  5 ⬜ RENDER         │      ↑ click → evidence panel opens          │
│                      │  ⚠ 2 low-confidence OCR values flagged      │
│ ITERATIONS 2/3       │  [ Approve ]  [ Reject + note ]              │
├──────────────────────┴──────────────────────────────────────────────┤
│ EVIDENCE  insp-2214 p.7                    │ RECEIPT      ← R16     │
│ ┌────────────────────────────┐             │ Egress: 3 internal     │
│ │ [page image, bbox in red]  │             │         0 external ✅  │
│ └────────────────────────────┘             │ Signature VALID        │
│ "Measured shell thickness 11.8 mm"         │ [Download receipt]     │
└─────────────────────────────────────────────────────────────────────┘
```

**Panel 1 — Status bar.** Poll `/health` every 10 s. Red immediately if any service is down,
and specifically red if the Tetragon monitor is not producing events — a dead monitor must never
look green.

**Panel 2 — Routing (R12).** Render `RouteDecision` verbatim for the current step: chosen model
in green with its reason, every rejected model in grey with its plain-English reason. This
panel is the R12 demo. Do not summarise it away.

**Panel 3 — Plan (R5, R7).** The step list with status icons, plus a visible
`Iterations: n/3` counter so re-planning is observable rather than hidden.

**Panel 4 — Deliverable + approval (R9, R13).** Show the `RenderPlan` as a readable draft, with
each grounded value rendered as `value [span_id]` where the span id is a clickable button that
loads Panel 5. Amber badge on `needs_review` values. Approve/Reject buttons POST to
`/tasks/{id}/approve`. Download button appears only after approval.

**Panel 5 — Evidence (the traceability payoff).** On span click: fetch
`/spans/{id}/crop` and the full page image, draw the bbox in red with PIL, show the span text
and confidence beneath. This click-through is the single most persuasive thing in the UI —
build it before any styling.

**Panel 6 — Receipt (R16).** Egress counts, signature validity, artifact hashes, download link.

---

## Build order inside this session

1. `api.py` endpoints + `tests/test_api.py` (mock `core.graph`) — get the contract right first.
2. Streamlit skeleton with the six panels wired to polling. Ugly is fine.
3. **Evidence click-through with bbox overlay.** Do this third, not last.
4. Routing panel.
5. Receipt panel.
6. Cosmetics, only if everything above works.

If you run low on context, ship 1–3 and record the rest in `PROGRESS.md`. A working evidence
panel with no styling beats a beautiful UI that can't prove provenance.

---

## Tests — `tests/test_api.py`

```python
def test_create_task_returns_id()
def test_get_task_returns_state()
def test_approve_resumes_graph(monkeypatch)
def test_artifact_download_rejects_path_traversal()   # ../../etc/passwd
def test_span_crop_returns_png()
def test_health_reports_all_services()
def test_reload_models_picks_up_new_manifest(tmp_path)   # live R4 demo
def test_no_endpoint_binds_0000()
```

---

## Definition of Done

```bash
pytest tests/test_api.py -v
make start
# then, in the browser at 127.0.0.1:8501:
#  - upload tests/fixtures/inspection_scanned.pdf, task type doc_to_deliverable
#  - routing panel shows chosen + rejected models with reasons
#  - plan advances through all steps
#  - clicking a span opens the page image with a red bbox
#  - Approve → .docx downloads and opens
#  - receipt panel shows 0 external egress, signature VALID
```

## Drift tripwires

- ❌ Building a chat interface, message history, or streaming tokens.
- ❌ React / Next.js / a component library. Streamlit only.
- ❌ Auth, login, user profiles, session management.
- ❌ Business logic in `api.py` or `ui.py`. Both are views over `core.*`.
- ❌ CDN-hosted fonts, CSS or JS — that is a live network call and breaks R1. Everything local.
- ❌ Charts, dashboards, analytics, dark-mode toggles.
- ❌ Showing a green monitor status when Tetragon is not producing events.

## Session exit

`PROGRESS.md`: which panels are complete, any polling/latency issue, screenshots taken.
`## Next action: FULL DEMO REHEARSAL — run docs/PROMPTS_PLAYBOOK.md §Rehearsal`
