"""L4 — tests for the six-node agent loop.

Non-integration tests never call a live model, sandbox, or Qdrant — they exercise pure
routing logic (_route_after_act/_route_after_verify), the plan-length schema constraint,
context trimming, verify's mechanical failure paths (which short-circuit before touching
any live service when the prerequisite data is simply missing), and the checkpoint/resume
mechanism in isolation via a tiny throwaway graph. Only the three end-to-end tests need a
live Ollama (+ sandbox/Qdrant for the render/coding paths) and are marked accordingly.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError
from typing_extensions import TypedDict

from core.config import SETTINGS
import core.graph as graph_module
from core.graph import (
    GRAPH,
    WorkbenchState,
    _NODE_NAMES,
    _route_after_act,
    _route_after_verify,
    node_verify,
    resume_task,
    run_task,
    trim_messages,
)
from core.schemas import EvidenceSpan, PlanStep, StepKind, TaskSpec, TaskType

FIXTURES = Path(__file__).parent / "fixtures"


def _span(span_id: str, text: str, *, needs_review: bool = False) -> EvidenceSpan:
    doc_id, rest = span_id.split("#")
    page = int(rest.split(".")[0][1:])
    return EvidenceSpan(
        span_id=span_id, doc_id=doc_id, page=page, bbox=(0.0, 0.0, 1.0, 0.1),
        text=text, confidence=0.9, extractor="native", needs_review=needs_review,
    )


def _base_state(**overrides) -> WorkbenchState:
    spec = TaskSpec(
        task_id="t-test-graph",
        task_type=TaskType.CODING,
        instruction="write a function",
        created_at=datetime.now(timezone.utc),
    )
    state: WorkbenchState = {
        "task_id": "t-test-graph",
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
        "messages": [{"role": "system", "content": "SYS"}],
    }
    state.update(overrides)
    return state


# ─────────────────────────── structural / anti-sprawl ──────────────────────────────


def test_graph_has_exactly_six_nodes():
    assert len(_NODE_NAMES) == 6
    graph_nodes = set(GRAPH.get_graph().nodes) - {"__start__", "__end__"}
    assert graph_nodes == set(_NODE_NAMES)


def test_plan_capped_at_eight_steps():
    step = lambda i: PlanStep(step_id=f"s{i}", kind=StepKind.LLM_CALL, description=f"step {i}")
    with pytest.raises(ValidationError):
        graph_module._Plan(steps=[step(i) for i in range(9)])
    # 8 is fine
    graph_module._Plan(steps=[step(i) for i in range(8)])


# ─────────────────────────── routing ────────────────────────────────────────────────


def test_act_routes_back_to_act_until_cursor_exhausts_plan():
    steps = [PlanStep(step_id="s1", kind=StepKind.LLM_CALL, description="x")] * 3
    state = _base_state(plan=steps, cursor=1)
    assert _route_after_act(state) == "act"
    state = _base_state(plan=steps, cursor=3)
    assert _route_after_act(state) == "verify"


def test_verify_failure_routes_back_to_plan():
    # CODING verify with no code/tests ever produced -> immediate, mechanical failure,
    # no sandbox needed.
    state = _base_state(iteration=0, status="acting")
    import asyncio

    result = asyncio.run(node_verify(state))
    assert result["status"] == "planning"
    assert result["iteration"] == 1
    assert result["verify_failures"]
    assert _route_after_verify({**state, **result}) == "plan_step"


def test_iteration_budget_forces_escalation():
    import asyncio

    state = _base_state(iteration=SETTINGS.agent.max_iterations - 1, status="acting")
    result = asyncio.run(node_verify(state))
    assert result["status"] == "escalated"
    assert result["iteration"] == SETTINGS.agent.max_iterations
    assert _route_after_verify({**state, **result}) == "approve"


# ─────────────────────────── context discipline ─────────────────────────────────────


def test_trim_messages_bounds_context():
    messages = [{"role": "system", "content": "SYS"}]
    for i in range(10):
        messages.append({"role": "observation", "content": f"obs-{i}"})
    evidence = [_span(f"doc#p1.b{i}", "x" * 1000) for i in range(20)]
    state = _base_state(messages=messages, evidence=evidence, verify_failures=["oops"])

    trimmed = trim_messages(state)

    assert trimmed[0] == {"role": "system", "content": "SYS"}
    assert any("TASK:" in m["content"] for m in trimmed)
    observation_msgs = [m for m in trimmed if "OBSERVATION:" in m["content"]]
    assert len(observation_msgs) == 2
    assert "obs-8" in observation_msgs[0]["content"]
    assert "obs-9" in observation_msgs[1]["content"]
    evidence_msgs = [m for m in trimmed if m["content"].startswith("EVIDENCE:")]
    assert len(evidence_msgs) == 1
    evidence_lines = evidence_msgs[0]["content"].splitlines()[1:]
    assert len(evidence_lines) == 12
    for line in evidence_lines:
        assert len(line) <= 320  # span_id prefix + 300 chars of text, generous slack
    assert any("PREVIOUS ATTEMPT FAILED" in m["content"] for m in trimmed)


# ─────────────────────────── checkpoint / resume (mechanism only) ──────────────────


class _TinyState(TypedDict):
    count: int
    approved: bool


def _build_tiny_graph(db_path: Path):
    def step_one(state: _TinyState) -> dict:
        return {"count": state["count"] + 1}

    def wait_for_human(state: _TinyState) -> dict:
        decision = interrupt({"count": state["count"]})
        return {"approved": bool(decision.get("approved"))}

    checkpointer = SqliteSaver(sqlite3.connect(str(db_path), check_same_thread=False))
    checkpointer.setup()
    g = StateGraph(_TinyState)
    g.add_node("step_one", step_one)
    g.add_node("wait_for_human", wait_for_human)
    g.add_edge(START, "step_one")
    g.add_edge("step_one", "wait_for_human")
    g.add_edge("wait_for_human", END)
    return g.compile(checkpointer=checkpointer)


def test_state_is_checkpointed_and_resumable(tmp_path):
    """Proves the exact mechanism run_task()/resume_task() rely on (SqliteSaver +
    interrupt() + Command(resume=...)) survives a process boundary — a fresh graph
    instance pointed at the same sqlite file, simulating a restart mid-task."""
    db_path = tmp_path / "checkpoints.sqlite"
    config = {"configurable": {"thread_id": "tiny-1"}}

    graph_a = _build_tiny_graph(db_path)
    result_a = graph_a.invoke({"count": 0, "approved": False}, config=config)
    assert result_a["count"] == 1
    assert graph_a.get_state(config).next == ("wait_for_human",)  # paused, not finished

    # "restart": brand-new graph + checkpointer instance, same sqlite file on disk.
    graph_b = _build_tiny_graph(db_path)
    result_b = graph_b.invoke(Command(resume={"approved": True}), config=config)
    assert result_b["count"] == 1
    assert result_b["approved"] is True


# ─────────────────────────── end-to-end (live services) ────────────────────────────


def _coding_spec() -> TaskSpec:
    return TaskSpec(
        task_id=f"t-test-coding-{datetime.now(timezone.utc):%H%M%S%f}",
        task_type=TaskType.CODING,
        instruction=(
            "Write a function `is_prime(n)` that returns True if n is prime. Also write a "
            "test that checks is_prime(97) is True AND deliberately asserts is_prime(1) is "
            "True (even though 1 is not prime), so the first verification attempt fails."
        ),
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_coding_task_end_to_end():
    """R14/R7: writes code, the deliberately-wrong first test fails verification, the loop
    re-plans, and it eventually passes (or exhausts the budget and escalates) — never
    infinite, always observable."""
    spec = _coding_spec()
    state = await run_task(spec)

    assert state["iteration"] >= 1, "the deliberately-wrong test should have forced at least one retry"
    assert state["status"] in ("awaiting_approval", "escalated")
    assert state.get("__interrupt__")

    final = await resume_task(spec.task_id, approval=True, note="test auto-approve")
    assert final["status"] == "done"
    assert final["artifacts"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_doc_to_deliverable_end_to_end():
    """R13: scan -> findings -> approval note, end to end."""
    scanned_pdf = FIXTURES / "inspection_scanned.pdf"
    spec = TaskSpec(
        task_id=f"t-test-approval-{datetime.now(timezone.utc):%H%M%S%f}",
        task_type=TaskType.DOC_TO_DELIVERABLE,
        instruction=(
            f"Ingest the inspection report at {scanned_pdf}, extract findings about vessel "
            "V-101's shell thickness, and produce a docx approval note."
        ),
        template_id="approval_note_v1",
        created_at=datetime.now(timezone.utc),
    )
    state = await run_task(spec)
    assert state.get("__interrupt__")
    assert state["render_plan"] is not None

    final = await resume_task(spec.task_id, approval=True, note="test auto-approve")
    assert final["status"] == "done"
    assert final["artifacts"]
    assert Path(final["artifacts"][-1]).is_file()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approval_interrupt_pauses_and_resumes():
    spec = _coding_spec()
    paused = await run_task(spec)
    assert paused.get("__interrupt__"), "graph must pause at APPROVE, not run straight through"
    assert paused["status"] in ("awaiting_approval", "escalated")

    resumed = await resume_task(spec.task_id, approval=False, note="rejected in test")
    assert resumed["status"] == "failed"
