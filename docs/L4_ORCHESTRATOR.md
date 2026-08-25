# L4 — AGENT ORCHESTRATOR

## MISSION LOCK

**Build:** the LangGraph state machine that plans multi-step work, executes it through L5 tools
and L6 retrieval, **verifies** the result, iterates on failure, and pauses for human approval.

**You are NOT building:** tools (L5), retrieval (L6), rendering (L7b), routing (L2), OCR (L3).
You **orchestrate** them. Every one is a function call you already have.

**Serves:** R5 (plans multi-step work), R7 (iterates instead of answering once), and it is the
spine of R13 and R14.

**Files You Own:**
```
core/graph.py
core/prompts.py
tests/test_graph.py
```

**This is the layer most likely to sprawl.** The graph is six nodes. If you find yourself
writing a seventh, stop and re-read this doc.

---

## The graph

```
                 ┌──────────┐
   TaskSpec ────►│ CLASSIFY │  determine required modalities, tokens, whether structured
                 └────┬─────┘
                      ▼
                 ┌──────────┐
                 │   PLAN   │◄────────────────┐  (re-plan on verify failure)
                 └────┬─────┘                 │
                      ▼                       │
                 ┌──────────┐                 │
            ┌───►│   ACT    │  executes plan[cursor], dispatching on StepKind
            │    └────┬─────┘                 │
            │         ▼                       │
            │   more steps? ──yes─────────────┘ (cursor += 1, back to ACT)
            │         │no                     │
            │         ▼                       │
            │    ┌──────────┐                 │
            │    │  VERIFY  │──fail & iter<max┘
            │    └────┬─────┘
            │         │pass  (or iter == max → escalate)
            │         ▼
            │    ┌──────────┐
            │    │ APPROVE  │  interrupt() — human gate, LangGraph pauses here
            │    └────┬─────┘
            │         ▼
            │    ┌──────────┐
            └────│   EMIT   │  render deliverable, close receipt
                 └──────────┘
```

`ACT` dispatches by `StepKind`:

| StepKind | Calls |
|---|---|
| `RETRIEVE` | `core.kb.search()` → append to `state.evidence` |
| `INGEST` | `core.ingest.ingest()` → `core.kb.index_spans()` |
| `EXECUTE_CODE` | `core.tools.call_tool("code.exec"/"code.test")` |
| `LLM_CALL` | `core.router.route_and_complete()` |
| `RENDER` | build `RenderPlan` via structured LLM call, then `core.render.render()` |

---

## `core/graph.py` — required shape

```python
"""L4 — the agent loop. Six nodes. No more."""

class WorkbenchState(TypedDict):
    task_id: str
    task_spec: TaskSpec
    plan: list[PlanStep]
    cursor: int
    evidence: list[EvidenceSpan]
    route_decisions: list[RouteDecision]
    tool_trace: list[ToolCall]
    render_plan: RenderPlan | None
    artifacts: list[str]
    verify_failures: list[str]
    iteration: int
    status: Literal["planning","acting","verifying","awaiting_approval","done","escalated","failed"]
    messages: list[dict]          # rolling scratchpad, TRIMMED — see below


async def node_classify(state) -> dict: ...
async def node_plan(state) -> dict: ...
async def node_act(state) -> dict: ...
async def node_verify(state) -> dict: ...
async def node_approve(state) -> dict: ...     # uses langgraph.types.interrupt()
async def node_emit(state) -> dict: ...

def build_graph() -> CompiledStateGraph:
    """StateGraph(WorkbenchState) with SqliteSaver checkpointer at
    SETTINGS.paths.data / 'checkpoints.sqlite'. Conditional edges:
      act   -> act | verify        (by cursor vs len(plan))
      verify-> plan | approve | emit  (fail+budget / pass / escalate)
    """

GRAPH = build_graph()

async def run_task(spec: TaskSpec) -> WorkbenchState: ...
async def resume_task(task_id: str, approval: bool, note: str = "") -> WorkbenchState: ...
```

### PLAN

One structured LLM call, routed through L2, constrained to:
```python
class _Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=8)
```
Cap at 8 steps. A plan longer than that on a hackathon demo is a runaway, not a capability.

Plan templates by `TaskType` live in `core/prompts.py`. For `DOC_TO_DELIVERABLE` the expected
shape is: `INGEST → RETRIEVE (SOP context) → LLM_CALL (extract findings) → EXECUTE_CODE
(calculations) → RENDER`. Give the model that as a worked example in the prompt; do not
hardcode it as a fixed pipeline, or you lose R5.

### VERIFY — this node is why R7 and R14 exist

Verification is **type-specific and mechanical**, never "ask the LLM if it looks right":

| Task type | Verification |
|---|---|
| `CODING` | `core.sandbox.run_tests()` must exit 0. This IS R14's "and verified". |
| `CALCULATION` | `core.sandbox.verify_calculation()` must report `agree=True`. |
| `DOC_TO_DELIVERABLE` | `core.render.validate_plan()` must pass — every `evidence_ref` resolves. |
| `DOC_QA` | every span id cited in the answer must exist via `core.kb.span_exists()`. |

On failure: append a specific, actionable message to `verify_failures`, increment `iteration`,
route back to `PLAN`. When `iteration >= SETTINGS.agent.max_iterations` (3), set
`status="escalated"` and go to `APPROVE` with the failures attached. **Never loop unbounded** —
on a shared single GPU that is a self-inflicted denial of service during your own demo.

### APPROVE

```python
decision = interrupt({
    "task_id": state["task_id"],
    "render_plan": state["render_plan"],
    "verify_failures": state["verify_failures"],
    "evidence_count": len(state["evidence"]),
    "needs_review_spans": [s.span_id for s in state["evidence"] if s.needs_review],
})
```
LangGraph pauses; the UI resumes with `Command(resume={"approved": True})`. The checkpointer
means a demo can survive a restart mid-task — use that, it is worth showing.

### Context discipline (do not skip)

`state["messages"]` grows without bound and will blow a 16 k coder context mid-demo. Before
every LLM call: keep the system message, the task instruction, the last 2 observations, and
**span summaries — never full span text**. Write `trim_messages(state)` and call it in one
place. Cap evidence passed into a prompt at 12 spans, truncated to 300 chars each.

---

## `core/prompts.py`

Every prompt in the system lives here, as a named constant. No f-strings scattered through
`graph.py`. Required: `CLASSIFY_PROMPT`, `PLAN_PROMPT_BY_TASKTYPE`, `EXTRACT_FINDINGS_PROMPT`,
`BUILD_RENDER_PLAN_PROMPT`, `WRITE_CODE_PROMPT`, `WRITE_TESTS_PROMPT`.

`BUILD_RENDER_PLAN_PROMPT` must state, verbatim:
> Every value you assert must include an `evidence_ref` naming a span id from the EVIDENCE
> list. If no span supports a value, omit the field entirely. Never invent a span id.
> Never estimate a number. If a value must be computed, set `computed_from` to the span ids of
> its inputs and put the arithmetic in `calculation`.

---

## Tests — `tests/test_graph.py`

```python
def test_graph_has_exactly_six_nodes()          # guards against sprawl
def test_plan_capped_at_eight_steps()
def test_verify_failure_routes_back_to_plan()
def test_iteration_budget_forces_escalation()   # never infinite
def test_trim_messages_bounds_context()
def test_state_is_checkpointed_and_resumable(tmp_path)

@pytest.mark.integration
async def test_coding_task_end_to_end()         # R14: writes code, tests fail, iterates, passes
async def test_doc_to_deliverable_end_to_end()  # R13: scan → findings → approval note
async def test_approval_interrupt_pauses_and_resumes()
```

`test_coding_task_end_to_end` should deliberately start from a prompt that produces a failing
test on the first attempt, so the iteration loop is *observably* exercised. That is R7's proof.

---

## Definition of Done

```bash
pytest tests/test_graph.py -v -m "not integration"
python -m core.graph --demo coding      # prints plan, each step, verify result, final artifact
python -m core.graph --demo approval    # R13 flagship, end to end
```

## Drift tripwires

- ❌ A seventh node. Six.
- ❌ Multi-agent / supervisor / crew patterns. One graph, one agent.
- ❌ Reimplementing a tool, retrieval, OCR or rendering inside a node.
- ❌ LLM-as-judge verification. Verification is mechanical.
- ❌ Unbounded iteration or unbounded plan length.
- ❌ Stuffing full documents into `messages`. Spans, summarised, capped.
- ❌ Calling `openai` or Qdrant directly. Go through `core.router` / `core.kb`.
- ❌ Adding memory, persona, or conversational history features. Not in the PS.

## Session exit

`PROGRESS.md`: observed iteration counts on the two demo tasks, wall-clock per task,
any prompt that needed rewording.
`## Next action: L8 — core/receipt.py + policies/ (Tetragon egress proof)`
