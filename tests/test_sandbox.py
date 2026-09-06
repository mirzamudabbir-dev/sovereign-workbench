"""L5 — tests for the gVisor sandbox and the four local tool families.

Every test below runs against a REAL docker daemon and a REAL, previously-built
`sovereign-sandbox:latest` image (`docker build -t sovereign-sandbox:latest sandbox/`).
None of it is mocked: this dev machine has a genuine Linux Docker backend (colima) with
`runsc` (gVisor) installed and registered as a runtime inside that VM — see PROGRESS.md,
Session 4 — so `SETTINGS.sandbox.runtime` really is exercised, not stubbed to `runc`.
"""
from __future__ import annotations

import shutil
import uuid

import docker
import pytest

from core.config import SETTINGS
from core.sandbox import run_python, run_tests, verify_calculation, workspace_for
from core.schemas import WorkbenchError
from core.tools import TOOL_REGISTRY, call_tool, fs_read, fs_write, sheet_read, sheet_write


@pytest.fixture
def task_id():
    tid = f"t-test-{uuid.uuid4().hex[:10]}"
    yield tid
    shutil.rmtree(workspace_for(tid), ignore_errors=True)


def _no_sandbox_containers() -> bool:
    client = docker.from_env()
    containers = client.containers.list(all=True, filters={"ancestor": SETTINGS.sandbox.image})
    return len(containers) == 0


# ─────────────────────────── sandbox execution ──────────────────────────────────


def test_hello_world_runs(task_id):
    result = run_python(task_id, "print('hello world')")
    assert result.exit_code == 0
    assert "hello world" in result.stdout
    assert not result.timed_out


def test_network_is_unreachable(task_id):
    code = """
import socket
try:
    socket.create_connection(("1.1.1.1", 80), timeout=2)
    print("REACHED")
except Exception as e:
    print("BLOCKED:", type(e).__name__)
"""
    result = run_python(task_id, code)
    assert "BLOCKED" in result.stdout
    assert "REACHED" not in result.stdout


def test_import_requests_fails(task_id):
    result = run_python(task_id, "import requests\nprint('should not get here')")
    assert result.exit_code != 0
    assert "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr


def test_timeout_kills_container(task_id):
    result = run_python(task_id, "import time\ntime.sleep(30)", timeout_s=2)
    assert result.timed_out is True
    assert result.duration_ms < 15_000


def test_container_always_removed(task_id):
    run_python(task_id, "raise RuntimeError('boom')")
    assert _no_sandbox_containers()


def test_runtime_is_runsc_or_documented_fallback():
    assert SETTINGS.sandbox.runtime in ("runsc", "runc")


def test_run_tests_reports_pytest_failure(task_id):
    code = "def add(a, b):\n    return a - b\n"  # deliberately wrong
    tests = "from solution import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    result = run_tests(task_id, code, tests)
    assert result.exit_code != 0
    assert "failed" in result.stdout.lower()


def test_run_tests_reports_pytest_success(task_id):
    code = "def add(a, b):\n    return a + b\n"
    tests = "from solution import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    result = run_tests(task_id, code, tests)
    assert result.exit_code == 0
    assert "1 passed" in result.stdout.lower()


# ─────────────────────────── verify_calculation ──────────────────────────────────


def test_verify_calculation_agrees_on_simple_case(task_id):
    # Base SI units: pint's magnitude equals the raw number, so Path A and Path B match.
    out = verify_calculation(
        task_id,
        expression="force / area",
        variables={"force": 1000.0, "area": 2.0},
        units={"force": "newton", "area": "meter ** 2"},
    )
    assert out["agree"] is True
    assert out["value_a"] == pytest.approx(500.0, rel=1e-6)
    assert out["value_b"] == pytest.approx(500.0, rel=1e-6)
    assert len(out["steps"]) > 0


def test_verify_calculation_flags_unit_mismatch(task_id):
    # `length` is declared in kilometres — pint normalises to base units (metres, x1000)
    # while sympy's raw substitution is unit-naive and just uses 1. The two paths must
    # disagree, which is exactly the class of bug this dual-path check exists to catch.
    out = verify_calculation(
        task_id,
        expression="length",
        variables={"length": 1.0},
        units={"length": "kilometer"},
    )
    assert out["agree"] is False
    assert out["value_a"] == pytest.approx(1000.0, rel=1e-6)
    assert out["value_b"] == pytest.approx(1.0, rel=1e-6)


def test_verify_calculation_raises_on_bad_expression(task_id):
    with pytest.raises(WorkbenchError):
        verify_calculation(task_id, expression="1 / 0", variables={}, units={})


# ─────────────────────────── path jail ───────────────────────────────────────────


def test_path_traversal_blocked(task_id):
    with pytest.raises(WorkbenchError):
        fs_read(task_id, {"path": "../../etc/passwd"})
    with pytest.raises(WorkbenchError):
        fs_write(task_id, {"path": "../../etc/passwd", "content": "pwned"})


def test_write_outside_workspace_requires_approval(task_id):
    outside_path = str(SETTINGS.paths.outputs / f"{task_id}-escape.txt")
    result = fs_write(task_id, {"path": outside_path, "content": "hello"})
    assert result["requires_approval"] is True
    assert result["written"] is False
    from pathlib import Path

    assert not Path(outside_path).exists()


def test_read_outside_workspace_and_uploads_is_hard_error(task_id):
    with pytest.raises(WorkbenchError):
        fs_read(task_id, {"path": "/etc/hosts"})


def test_fs_write_then_read_round_trips_inside_workspace(task_id):
    write_result = fs_write(task_id, {"path": "notes.txt", "content": "hello sovereign"})
    assert write_result["requires_approval"] is False
    assert write_result["written"] is True
    assert fs_read(task_id, {"path": "notes.txt"}) == "hello sovereign"


# ─────────────────────────── spreadsheet tools ───────────────────────────────────


def test_sheet_write_then_read_round_trips(task_id):
    rows = [["item", "qty"], ["bolt", 10], ["nut", 20]]
    write_result = sheet_write(task_id, {"path": "inventory.xlsx", "rows": rows})
    assert write_result["written"] is True

    read_result = sheet_read(task_id, {"path": "inventory.xlsx"})
    assert read_result["rows"] == rows


# ─────────────────────────── call_tool / registry ────────────────────────────────


def test_tool_registry_has_exactly_seven_tools():
    assert set(TOOL_REGISTRY) == {
        "fs.read",
        "fs.write",
        "code.exec",
        "code.test",
        "sheet.read",
        "sheet.write",
        "kb.search",
    }


def test_call_tool_returns_toolcall_record(task_id):
    result, tool_call = call_tool(
        task_id, "s1", "fs.write", {"path": "hello.txt", "content": "hi"}
    )
    assert result["written"] is True
    assert tool_call.tool_name == "fs.write"
    assert tool_call.step_id == "s1"
    assert tool_call.ok is True
    assert tool_call.error is None
    assert len(tool_call.args_sha256) == 64
    assert tool_call.duration_ms >= 0


def test_call_tool_reraises_workbench_error_with_attached_record(task_id):
    with pytest.raises(WorkbenchError) as excinfo:
        call_tool(task_id, "s1", "fs.read", {"path": "../../etc/passwd"})
    assert excinfo.value.tool_call.ok is False
    assert excinfo.value.tool_call.error is not None


def test_call_tool_unknown_tool_raises(task_id):
    with pytest.raises(WorkbenchError):
        call_tool(task_id, "s1", "shell.exec", {})


def test_kb_search_delegates_and_fails_loudly_until_l6_exists(task_id):
    # core/kb.py is L6 — not built yet. This must fail loudly (WorkbenchError), never
    # silently return an empty result, and it must not implement retrieval itself.
    with pytest.raises(WorkbenchError):
        call_tool(task_id, "s1", "kb.search", {"query": "pressure vessel inspection"})


def test_code_exec_via_call_tool_runs_in_sandbox(task_id):
    result, tool_call = call_tool(
        task_id, "s1", "code.exec", {"code": "print(2 + 2)"}
    )
    assert result["exit_code"] == 0
    assert "4" in result["stdout"]
    assert tool_call.ok is True


def test_code_test_via_call_tool_is_r14_run_and_verified(task_id):
    result, _ = call_tool(
        task_id,
        "s1",
        "code.test",
        {
            "code": "def square(x):\n    return x * x\n",
            "tests": "from solution import square\n\ndef test_square():\n    assert square(3) == 9\n",
        },
    )
    assert result["exit_code"] == 0
    assert "1 passed" in result["stdout"].lower()
