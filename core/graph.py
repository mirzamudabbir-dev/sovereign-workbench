"""L4 — the agent loop. Six nodes. No more.

classify -> plan -> act (loops on itself) -> verify -> plan | approve -> emit

Orchestrates L2 (routing), L3 (ingestion), L5 (tools/sandbox), L6 (retrieval) and L7b
(rendering) — every one of those is a function call this module already has. Nothing here
reimplements a tool, retrieval, OCR or rendering; nothing here calls openai or Qdrant
directly, only core.router.route_and_complete() and core.kb's public functions.
"""
from __future__ import annotations

import argparse
import asyncio
import atexit
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from core.config import SETTINGS
from core.ingest import ingest
from core.kb import index_spans, search, span_exists
from core.prompts import (
    ANSWER_QUESTION_PROMPT,
    BUILD_RENDER_PLAN_PROMPT,
    CLASSIFY_PROMPT,
    DERIVE_CALCULATION_PROMPT,
    EXTRACT_FINDINGS_PROMPT,
    PLAN_PROMPT_BY_TASKTYPE,
    WRITE_CODE_PROMPT,
    WRITE_TESTS_PROMPT,
)
from core.receipt import build_receipt, write_receipt
from core.render import EvidenceResolutionError, render, validate_plan
from core.router import RouteRequest, route_and_complete
from core.sandbox import run_tests, verify_calculation, workspace_for
from core.schemas import (
    EvidenceSpan,
    Finding,
    PlanStep,
    RenderPlan,
    RouteDecision,
    StepKind,
    TaskSpec,
    TaskType,
    ToolCall,
    WorkbenchError,
)
from core.serving import estimate_tokens
from core.tools import call_tool

logger = logging.getLogger(__name__)

_MAX_EVIDENCE_FOR_PROMPT = 12
_MAX_SPAN_CHARS = 300
_MAX_OBSERVATIONS = 2


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
    status: Literal[
        "planning", "acting", "verifying", "awaiting_approval", "done", "escalated", "failed"
    ]
    messages: list[dict]


# ─────────────────────────── context discipline ─────────────────────────────────────


def trim_messages(state: WorkbenchState) -> list[dict]:
    """Keep the system message, the task instruction, the last 2 observations, and span
    SUMMARIES — never full span text. Cap evidence at 12 spans truncated to 300 chars.
    Called from exactly one place: `_call_llm()`, immediately before every LLM call."""
    messages: list[dict] = []

    system_msgs = [m for m in state["messages"] if m.get("role") == "system"]
    if system_msgs:
        messages.append(system_msgs[0])

    messages.append({"role": "user", "content": f"TASK: {state['task_spec'].instruction}"})

    observations = [m for m in state["messages"] if m.get("role") == "observation"]
    for obs in observations[-_MAX_OBSERVATIONS:]:
        messages.append({"role": "user", "content": f"OBSERVATION: {obs['content']}"})

    if state["verify_failures"]:
        messages.append(
            {"role": "user", "content": "PREVIOUS ATTEMPT FAILED:\n" + "\n".join(state["verify_failures"])}
        )

    evidence = state["evidence"][:_MAX_EVIDENCE_FOR_PROMPT]
    if evidence:
        lines = [f"[{s.span_id}] {s.text[:_MAX_SPAN_CHARS]}" for s in evidence]
        messages.append({"role": "user", "content": "EVIDENCE:\n" + "\n".join(lines)})

    return messages


async def _call_llm(
    state: WorkbenchState,
    step_id: str,
    prompt: str,
    *,
    schema_model: type[BaseModel] | None = None,
    extra_context: str | None = None,
) -> tuple[Any, RouteDecision]:
    """The one place every LLM call in this module goes through — trims context, appends
    the task-specific instruction (a named constant from core.prompts), routes via L2."""
    messages = trim_messages(state)
    if extra_context:
        messages.append({"role": "user", "content": extra_context})
    messages.append({"role": "user", "content": prompt})

    req = RouteRequest(
        step_id=step_id,
        task_type=state["task_spec"].task_type,
        instruction=state["task_spec"].instruction,
        needs_structured_output=schema_model is not None,
        estimated_tokens=estimate_tokens(messages),
    )
    return await route_and_complete(req, messages, schema_model=schema_model)


def _append_message(state: WorkbenchState, role: str, content: str) -> list[dict]:
    messages = list(state["messages"])
    messages.append({"role": role, "content": content})
    return messages


def _find_prior_result(plan: list[PlanStep], upto: int, key: str) -> dict | None:
    """Scan already-executed steps (payload["result"]) for the most recent one carrying
    `key` — how ACT threads one step's output into a later step without a 7th state field."""
    for step in reversed(plan[:upto]):
        result = step.payload.get("result")
        if isinstance(result, dict) and key in result:
            return result
    return None


# ─────────────────────────── CLASSIFY ───────────────────────────────────────────────


async def node_classify(state: WorkbenchState) -> dict:
    """Cheap and mechanical, no LLM call: establishes the system message every later LLM
    call will see (via trim_messages), and records a rough classification for PLAN."""
    spec = state["task_spec"]
    messages = [{"role": "system", "content": CLASSIFY_PROMPT}]

    estimated_tokens = estimate_tokens([{"role": "user", "content": spec.instruction}])
    likely_visual = any(
        kw in spec.instruction.lower() for kw in ("image", "drawing", "photo", "scan", "scanned")
    )
    messages.append(
        {
            "role": "observation",
            "content": (
                f"classify: task_type={spec.task_type.value} estimated_tokens={estimated_tokens} "
                f"likely_visual={likely_visual} doc_ids={spec.doc_ids}"
            ),
        }
    )
    return {"messages": messages, "status": "planning"}


# ─────────────────────────── PLAN ───────────────────────────────────────────────────


class _Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=8)


async def node_plan(state: WorkbenchState) -> dict:
    """One structured LLM call, capped at 8 steps. Re-invoked on verify failure with the
    failure messages already folded into context by trim_messages()."""
    spec = state["task_spec"]
    prompt = PLAN_PROMPT_BY_TASKTYPE[spec.task_type]
    step_id = f"{state['task_id']}.plan.{state['iteration']}"

    result, decision = await _call_llm(state, step_id, prompt, schema_model=_Plan)
    plan_steps: list[PlanStep] = result.steps[:8]
    for i, step in enumerate(plan_steps, start=1):
        step.step_id = f"{state['task_id']}.s{i}"
        step.done = False
        step.output_summary = None
        step.payload = dict(step.payload)

    route_decisions = [*state["route_decisions"], decision]
    messages = _append_message(
        state, "observation", f"plan: {len(plan_steps)} steps — " + "; ".join(s.description for s in plan_steps)
    )
    return {
        "plan": plan_steps,
        "cursor": 0,
        "route_decisions": route_decisions,
        "messages": messages,
        "status": "acting",
    }


# ─────────────────────────── ACT ────────────────────────────────────────────────────


class _CodeArtifact(BaseModel):
    code: str


class _FindingsOutput(BaseModel):
    findings: list[Finding] = Field(min_length=1, max_length=10)


class _CalcInputs(BaseModel):
    expression: str
    variables: dict[str, float]
    units: dict[str, str] = {}


async def _act_retrieve(state: WorkbenchState, step: PlanStep) -> tuple[str, list[EvidenceSpan]]:
    query = step.payload.get("query") or state["task_spec"].instruction
    doc_ids = step.payload.get("doc_ids") or (state["task_spec"].doc_ids or None)
    results = search(query, top_k=step.payload.get("top_k", 8), doc_ids=doc_ids)
    spans = [r.span for r in results]
    step.payload["result"] = {"span_ids": [s.span_id for s in spans]}
    return f"retrieved {len(spans)} spans for query {query!r}", spans


def _act_ingest(step: PlanStep) -> tuple[str, str]:
    path = Path(step.payload["path"])
    ref, spans = ingest(path)
    count = index_spans(spans, ref)
    step.payload["result"] = {"doc_id": ref.doc_id, "span_count": count}
    return f"ingested {path.name} -> doc_id={ref.doc_id}, {count} spans", ref.doc_id


async def _act_llm_call(state: WorkbenchState, step: PlanStep) -> tuple[str, RouteDecision]:
    task_type = state["task_spec"].task_type
    desc = step.description.lower()

    if task_type == TaskType.CODING:
        if "test" in desc:
            code_result = _find_prior_result(state["plan"], state["cursor"], "code")
            extra = f"SOLUTION CODE:\n{code_result['code']}" if code_result else None
            result, decision = await _call_llm(
                state, step.step_id, WRITE_TESTS_PROMPT, schema_model=_CodeArtifact, extra_context=extra
            )
            step.payload["result"] = {"tests": result.code}
            return f"wrote tests ({len(result.code)} chars)", decision
        result, decision = await _call_llm(state, step.step_id, WRITE_CODE_PROMPT, schema_model=_CodeArtifact)
        step.payload["result"] = {"code": result.code}
        return f"wrote solution code ({len(result.code)} chars)", decision

    if task_type == TaskType.DOC_TO_DELIVERABLE:
        result, decision = await _call_llm(
            state, step.step_id, EXTRACT_FINDINGS_PROMPT, schema_model=_FindingsOutput
        )
        step.payload["result"] = {"findings": [f.model_dump() for f in result.findings]}
        return f"extracted {len(result.findings)} findings", decision

    if task_type == TaskType.DOC_QA:
        answer, decision = await _call_llm(state, step.step_id, ANSWER_QUESTION_PROMPT)
        step.payload["result"] = {"answer": answer}
        return f"answered: {answer[:200]}", decision

    if task_type == TaskType.CALCULATION:
        result, decision = await _call_llm(
            state, step.step_id, DERIVE_CALCULATION_PROMPT, schema_model=_CalcInputs
        )
        step.payload["result"] = {
            "expression": result.expression, "variables": result.variables, "units": result.units,
        }
        return f"derived expression: {result.expression}", decision

    raise WorkbenchError(f"no LLM_CALL handling for task type {task_type!r}")


def _act_execute_code(state: WorkbenchState, step: PlanStep) -> tuple[str, ToolCall | None]:
    task_id = state["task_id"]
    calc_input = step.payload if "expression" in step.payload else _find_prior_result(
        state["plan"], state["cursor"], "expression"
    )
    if calc_input:
        result = verify_calculation(
            task_id, calc_input["expression"], calc_input["variables"], calc_input.get("units", {})
        )
        step.payload["result"] = {"calc": result}
        return f"calculation: agree={result['agree']} value={result['value_a']} {result['unit']}", None

    code_result = _find_prior_result(state["plan"], state["cursor"], "code")
    tests_result = _find_prior_result(state["plan"], state["cursor"], "tests")
    code = code_result["code"] if code_result else step.payload.get("code", "")
    tests = tests_result["tests"] if tests_result else step.payload.get("tests", "")
    if not code:
        return "no code available to execute for this step", None

    if tests:
        sandbox_result, tool_call = call_tool(task_id, step.step_id, "code.test", {"code": code, "tests": tests})
    else:
        sandbox_result, tool_call = call_tool(task_id, step.step_id, "code.exec", {"code": code})
    step.payload["result"] = {"sandbox": sandbox_result}
    return f"ran code: exit_code={sandbox_result['exit_code']} timed_out={sandbox_result['timed_out']}", tool_call


async def _act_render(state: WorkbenchState, step: PlanStep) -> tuple[str, RenderPlan, RouteDecision]:
    findings_result = _find_prior_result(state["plan"], state["cursor"], "findings")
    extra = None
    if findings_result:
        extra = "PRE-EXTRACTED FINDINGS (reuse these, same evidence_refs):\n" + str(findings_result["findings"])
    output_format = step.payload.get("output_format", "docx")
    prompt = BUILD_RENDER_PLAN_PROMPT + f"\n\nRequired output_format: {output_format!r}."

    result, decision = await _call_llm(
        state, step.step_id, prompt, schema_model=RenderPlan, extra_context=extra
    )
    step.payload["result"] = {"render_plan": result.model_dump(mode="json")}
    return f"built RenderPlan {result.title!r} ({len(result.fields)} fields, {len(result.findings)} findings)", result, decision


async def node_act(state: WorkbenchState) -> dict:
    """Executes plan[cursor], dispatching purely on StepKind. Never re-implements a tool,
    retrieval, OCR or rendering call — every branch below is one function call to another
    layer. Exceptions are caught and recorded as an observation; VERIFY (not ACT) decides
    pass/fail, mechanically and independently of whatever ACT recorded here."""
    step = state["plan"][state["cursor"]]
    task_spec = state["task_spec"]
    evidence = list(state["evidence"])
    tool_trace = list(state["tool_trace"])
    route_decisions = list(state["route_decisions"])
    render_plan_update: RenderPlan | None = None
    observation = ""

    try:
        if step.kind == StepKind.RETRIEVE:
            observation, new_spans = await _act_retrieve(state, step)
            known_ids = {s.span_id for s in evidence}
            evidence.extend(s for s in new_spans if s.span_id not in known_ids)

        elif step.kind == StepKind.INGEST:
            observation, new_doc_id = _act_ingest(step)
            if new_doc_id and new_doc_id not in task_spec.doc_ids:
                task_spec = task_spec.model_copy(update={"doc_ids": [*task_spec.doc_ids, new_doc_id]})

        elif step.kind == StepKind.LLM_CALL:
            observation, decision = await _act_llm_call(state, step)
            route_decisions.append(decision)

        elif step.kind == StepKind.EXECUTE_CODE:
            observation, tool_call_record = _act_execute_code(state, step)
            if tool_call_record is not None:
                tool_trace.append(tool_call_record)

        elif step.kind == StepKind.RENDER:
            observation, render_plan_update, decision = await _act_render(state, step)
            route_decisions.append(decision)

        else:
            observation = f"unhandled step kind: {step.kind}"

    except WorkbenchError as exc:
        observation = f"step {step.step_id} FAILED: {exc}"
        logger.error(observation)

    step.done = True
    step.output_summary = observation[:500]

    updates: dict[str, Any] = {
        "plan": state["plan"],
        "cursor": state["cursor"] + 1,
        "evidence": evidence,
        "tool_trace": tool_trace,
        "route_decisions": route_decisions,
        "messages": _append_message(state, "observation", observation),
        "task_spec": task_spec,
        "status": "acting",
    }
    if render_plan_update is not None:
        updates["render_plan"] = render_plan_update
    return updates


def _route_after_act(state: WorkbenchState) -> Literal["act", "verify"]:
    return "act" if state["cursor"] < len(state["plan"]) else "verify"


# ─────────────────────────── VERIFY ─────────────────────────────────────────────────

_SPAN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*#p\d+\.b\d+")


def _verify_coding(state: WorkbenchState) -> list[str]:
    code_result = _find_prior_result(state["plan"], len(state["plan"]), "code")
    tests_result = _find_prior_result(state["plan"], len(state["plan"]), "tests")
    if not code_result or not tests_result:
        return ["no code and/or tests were produced by the plan — add llm_call steps for both"]

    result = run_tests(state["task_id"], code_result["code"], tests_result["tests"])
    if result.exit_code != 0:
        tail = (result.stdout[-800:] + "\n" + result.stderr[-800:]).strip()
        return [f"pytest exited {result.exit_code} (must be 0): {tail}"]
    return []


def _verify_calculation(state: WorkbenchState) -> list[str]:
    calc_result = _find_prior_result(state["plan"], len(state["plan"]), "calc")
    if not calc_result:
        return ["no calculation was performed — add an execute_code step"]
    calc = calc_result["calc"]
    if not calc["agree"]:
        return [f"independent re-derivation disagreed (Path A={calc['value_a']}, Path B={calc['value_b']})"]
    return []


def _verify_doc_to_deliverable(state: WorkbenchState) -> list[str]:
    if state["render_plan"] is None:
        return ["no RenderPlan was produced — add a render step"]
    try:
        validate_plan(state["render_plan"])
    except (EvidenceResolutionError, WorkbenchError) as exc:
        return [f"render plan failed evidence validation: {exc}"]
    return []


def _verify_doc_qa(state: WorkbenchState) -> list[str]:
    answer_result = _find_prior_result(state["plan"], len(state["plan"]), "answer")
    if not answer_result:
        return ["no answer was produced — add an llm_call step"]
    cited = _SPAN_ID_RE.findall(answer_result["answer"])
    if not cited:
        return ["answer cites no evidence span ids — every fact must cite one"]
    failures = [f"answer cites nonexistent span id: {sid}" for sid in cited if not span_exists(sid)]
    return failures


_VERIFIERS = {
    TaskType.CODING: _verify_coding,
    TaskType.CALCULATION: _verify_calculation,
    TaskType.DOC_TO_DELIVERABLE: _verify_doc_to_deliverable,
    TaskType.DOC_QA: _verify_doc_qa,
}


async def node_verify(state: WorkbenchState) -> dict:
    """Mechanical and type-specific. Never asks the LLM if the result 'looks right'."""
    failures = _VERIFIERS[state["task_spec"].task_type](state)

    if not failures:
        return {"verify_failures": [], "status": "awaiting_approval"}

    iteration = state["iteration"] + 1
    messages = _append_message(state, "observation", "verify failed: " + "; ".join(failures))
    if iteration >= SETTINGS.agent.max_iterations:
        return {"verify_failures": failures, "iteration": iteration, "status": "escalated", "messages": messages}
    return {"verify_failures": failures, "iteration": iteration, "status": "planning", "messages": messages}


def _route_after_verify(state: WorkbenchState) -> Literal["plan_step", "approve"]:
    return "plan_step" if state["status"] == "planning" else "approve"


# ─────────────────────────── APPROVE ────────────────────────────────────────────────


async def node_approve(state: WorkbenchState) -> dict:
    """Human gate. LangGraph pauses here via interrupt() until resume_task() provides a
    decision. Reached both on a clean verify pass and on escalation (budget exhausted) —
    either way a human sees the failures (if any) and the needs_review spans before
    anything is written to disk.

    Every state access below uses .get(), not state[...] — proven necessary, not
    defensive-for-its-own-sake: LangGraph 0.2.60 drops any WorkbenchState channel that
    was set only by the initial input and never rewritten by a later node (e.g.
    render_plan on a CODING/DOC_QA run, or evidence on a run with no RETRIEVE step) from
    the state dict handed to a node that is REPLAYED after interrupt()/resume — direct
    bracket access raises KeyError on resume in exactly that case. Confirmed by a
    minimal reproduction using the real WorkbenchState/PlanStep types before this fix
    was written; see PROGRESS.md Session 9."""
    decision = interrupt(
        {
            "task_id": state.get("task_id"),
            "render_plan": state.get("render_plan"),
            "verify_failures": state.get("verify_failures", []),
            "evidence_count": len(state.get("evidence", [])),
            "needs_review_spans": [s.span_id for s in state.get("evidence", []) if s.needs_review],
        }
    )
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    note = decision.get("note", "") if isinstance(decision, dict) else ""

    messages = _append_message(state, "observation", f"human approval={approved} note={note!r}")
    return {"status": "done" if approved else "failed", "messages": messages}


# ─────────────────────────── EMIT ───────────────────────────────────────────────────


async def node_emit(state: WorkbenchState) -> dict:
    """Renders the deliverable (if any), finalises artifacts, and closes the L8 receipt.
    A human already approved with full visibility of needs_review spans in APPROVE's
    interrupt payload, so allow_review_spans=True here is that approval being honoured,
    not a bypass.

    The receipt call is the ONLY coupling to L8 (core.receipt), per docs/L8_AUDIT.md's
    own text: "L4's node_emit calls build_receipt() then write_receipt()." L8 observes;
    it must never block a task — if the egress monitor isn't running (e.g. no Tetragon/
    pktap capture on this host), build_receipt() raises, and that is logged and
    swallowed here rather than failing an otherwise-successful, human-approved task.

    Every state access below uses .get() — see node_approve's docstring for why this is
    a proven necessity, not defensive-for-its-own-sake, on the post-resume path. `artifacts`
    and `render_plan` are exactly the "written only at init, never again" shape that
    triggers the bug for any task type that skips RENDER (CODING, DOC_QA); `tool_trace`
    is equally at risk for any task that never hits EXECUTE_CODE.
    """
    task_id = state.get("task_id")
    task_spec = state.get("task_spec")
    artifacts = list(state.get("artifacts", []))

    if state.get("status") == "failed":
        return {"artifacts": artifacts}

    render_plan = state.get("render_plan")
    if render_plan is not None:
        path = render(render_plan, task_id, allow_review_spans=True)
        artifacts.append(str(path))
    else:
        ws = workspace_for(task_id)
        artifacts.extend(sorted(str(p) for p in ws.glob("*") if p.is_file()))

    if task_spec is None:
        logger.warning("task_spec missing from state for task %s — cannot build L8 receipt", task_id)
    else:
        try:
            receipt = build_receipt(
                task_id,
                task_spec.created_at,
                datetime.now(timezone.utc),
                state.get("route_decisions", []),
                state.get("tool_trace", []),
                [Path(a) for a in artifacts],
            )
            write_receipt(receipt)
        except WorkbenchError as exc:
            logger.warning("could not build/write L8 receipt for task %s: %s", task_id, exc)

    return {"artifacts": artifacts, "status": "done"}


# ─────────────────────────── graph assembly ─────────────────────────────────────────

#  The PLAN node is registered as "plan_step", not "plan" — LangGraph refuses a node name
#  that collides with a state key, and WorkbenchState's `plan` field is required verbatim
#  by the doc. Six nodes either way; this is a naming workaround, not a design change.
_NODE_NAMES = ("classify", "plan_step", "act", "verify", "approve", "emit")

_DB_PATH = SETTINGS.paths.data / "checkpoints.sqlite"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _build_checkpointer() -> AsyncSqliteSaver:
    """core/graph.py is async end to end (every node is `async def`, run_task()/
    resume_task() use .ainvoke()) — the sync `SqliteSaver` the doc names raises
    NotImplementedError on any async method in this langgraph version. AsyncSqliteSaver is
    the async-capable sibling of the same idea: still a plain SqliteSaver-family
    checkpointer at SETTINGS.paths.data/'checkpoints.sqlite', just one that doesn't block
    (or crash) the event loop. Built via a throwaway asyncio.run() at import time since
    `GRAPH = build_graph()` must stay a plain synchronous module-level assignment."""

    async def _connect() -> AsyncSqliteSaver:
        conn = await aiosqlite.connect(str(_DB_PATH))
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        return saver

    return asyncio.run(_connect())


_CHECKPOINTER = _build_checkpointer()


def _close_checkpointer() -> None:
    """aiosqlite keeps a non-daemon worker thread alive until its connection is closed
    explicitly — without this, any process that imports this module hangs on exit
    (verified: `python -c "import core.graph"` never returns without it). Registered
    with atexit rather than an explicit call site, since callers of run_task()/
    resume_task() (the CLI, pytest) shouldn't have to know this detail exists."""
    try:
        asyncio.run(_CHECKPOINTER.conn.close())
    except Exception:
        pass


atexit.register(_close_checkpointer)


def build_graph() -> CompiledStateGraph:
    """StateGraph(WorkbenchState) with SqliteSaver checkpointer at
    SETTINGS.paths.data / 'checkpoints.sqlite'. Conditional edges:
      act   -> act | verify           (by cursor vs len(plan))
      verify-> plan_step | approve    (fail+budget -> plan_step; pass or escalate -> approve)
    """
    graph = StateGraph(WorkbenchState)
    graph.add_node("classify", node_classify)
    graph.add_node("plan_step", node_plan)
    graph.add_node("act", node_act)
    graph.add_node("verify", node_verify)
    graph.add_node("approve", node_approve)
    graph.add_node("emit", node_emit)

    graph.add_edge(START, "classify")
    graph.add_edge("classify", "plan_step")
    graph.add_edge("plan_step", "act")
    graph.add_conditional_edges("act", _route_after_act, {"act": "act", "verify": "verify"})
    graph.add_conditional_edges("verify", _route_after_verify, {"plan_step": "plan_step", "approve": "approve"})
    graph.add_edge("approve", "emit")
    graph.add_edge("emit", END)

    return graph.compile(checkpointer=_CHECKPOINTER)


GRAPH = build_graph()


def _initial_state(spec: TaskSpec) -> WorkbenchState:
    return {
        "task_id": spec.task_id,
        "task_spec": spec,
        "plan": [],
        "cursor": 0,
        "evidence": [],
        "route_decisions": [],
        "tool_trace": [],
        "render_plan": None,
        "artifacts": [],
        "verify_failures": [],
        "iteration": 0,
        "status": "planning",
        "messages": [],
    }


async def _with_interrupt_info(result: dict, config: dict) -> dict:
    """LangGraph 0.2.x's ainvoke() return value does not itself carry a pending
    interrupt — it lives on the checkpoint snapshot's pending tasks. Surface it under
    `__interrupt__` anyway so callers (the demo CLI, tests) have one place to check
    "is this task paused", regardless of langgraph version quirks."""
    snapshot = await GRAPH.aget_state(config)
    interrupts = tuple(i for task in snapshot.tasks for i in task.interrupts)
    if interrupts:
        result = dict(result)
        result["__interrupt__"] = interrupts
    return result


async def run_task(spec: TaskSpec) -> WorkbenchState:
    config = {"configurable": {"thread_id": spec.task_id}}
    result = await GRAPH.ainvoke(_initial_state(spec), config=config)
    return await _with_interrupt_info(result, config)


async def resume_task(task_id: str, approval: bool, note: str = "") -> WorkbenchState:
    config = {"configurable": {"thread_id": task_id}}
    result = await GRAPH.ainvoke(Command(resume={"approved": approval, "note": note}), config=config)
    return await _with_interrupt_info(result, config)


# ─────────────────────────── demo CLI ───────────────────────────────────────────────


def _new_task_id() -> str:
    return f"t-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:6]}"


def _print_result(state: WorkbenchState) -> None:
    print(f"status: {state.get('status')}")
    plan = state.get("plan", [])
    print(f"plan ({len(plan)} steps):")
    for step in plan:
        print(f"  [{'x' if step.done else ' '}] {step.step_id} ({step.kind.value}): {step.description}")
        if step.output_summary:
            print(f"        -> {step.output_summary}")
    if state.get("verify_failures"):
        print("verify failures:")
        for f in state["verify_failures"]:
            print(f"  - {f}")
    print(f"iteration: {state.get('iteration')}")
    interrupts = state.get("__interrupt__")
    if interrupts:
        print("PAUSED — awaiting human approval:")
        payload = interrupts[0].value
        print(f"  evidence_count: {payload['evidence_count']}")
        print(f"  needs_review_spans: {payload['needs_review_spans']}")
        print(f"  verify_failures: {payload['verify_failures']}")
    for artifact in state.get("artifacts", []):
        print(f"artifact: {artifact}")


async def _demo_coding() -> None:
    spec = TaskSpec(
        task_id=_new_task_id(),
        task_type=TaskType.CODING,
        instruction=(
            "Write a function `is_prime(n)` that returns True if n is a prime number, "
            "False otherwise. Also write a test that checks is_prime(97) is True AND "
            "deliberately asserts is_prime(1) is True (even though 1 is not prime) so the "
            "first verification attempt fails and must be corrected."
        ),
        doc_ids=[],
        created_at=datetime.now(timezone.utc),
    )
    t0 = time.monotonic()
    state = await run_task(spec)
    print(f"=== CODING DEMO ({time.monotonic() - t0:.1f}s) ===")
    _print_result(state)
    if state.get("__interrupt__"):
        state = await resume_task(spec.task_id, approval=True, note="demo auto-approve")
        _print_result(state)
    print(f"=== total wall-clock: {time.monotonic() - t0:.1f}s ===")


async def _demo_approval() -> None:
    fixtures = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    scanned_pdf = fixtures / "inspection_scanned.pdf"
    spec = TaskSpec(
        task_id=_new_task_id(),
        task_type=TaskType.DOC_TO_DELIVERABLE,
        instruction=(
            f"Ingest the inspection report at {scanned_pdf}, extract the findings about "
            "vessel V-101's shell thickness, and produce a docx approval note recommending "
            "whether to approve continued service."
        ),
        doc_ids=[],
        template_id="approval_note_v1",
        created_at=datetime.now(timezone.utc),
    )
    t0 = time.monotonic()
    state = await run_task(spec)
    print(f"=== APPROVAL DEMO ({time.monotonic() - t0:.1f}s) ===")
    _print_result(state)
    if state.get("__interrupt__"):
        state = await resume_task(spec.task_id, approval=True, note="demo auto-approve")
        _print_result(state)
    print(f"=== total wall-clock: {time.monotonic() - t0:.1f}s ===")


async def _demo_doc_qa() -> None:
    """R15's flagship: a plain question answered from the KB, every fact cited by span
    id, verified mechanically (core.graph._verify_doc_qa) rather than "does this look
    right". Relies on the KB already holding indexed spans — see
    scripts/index_corpus.py; earlier sessions' fixture ingests already populated the
    live Qdrant collection with V-101 shell-thickness content, which is what this asks
    about. Doubles as the "normal task keeps working" step in
    scripts/negative_control.sh."""
    spec = TaskSpec(
        task_id=_new_task_id(),
        task_type=TaskType.DOC_QA,
        instruction="What does the inspection report say about vessel V-101's shell thickness?",
        doc_ids=[],
        created_at=datetime.now(timezone.utc),
    )
    t0 = time.monotonic()
    state = await run_task(spec)
    print(f"=== DOC_QA DEMO ({time.monotonic() - t0:.1f}s) ===")
    _print_result(state)
    if state.get("__interrupt__"):
        state = await resume_task(spec.task_id, approval=True, note="demo auto-approve")
        _print_result(state)
    print(f"=== total wall-clock: {time.monotonic() - t0:.1f}s ===")


_DEMOS = {"coding": _demo_coding, "approval": _demo_approval, "doc_qa": _demo_doc_qa}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", choices=sorted(_DEMOS), required=True)
    args = parser.parse_args()
    asyncio.run(_DEMOS[args.demo]())


if __name__ == "__main__":
    main()
