"""L5 — gVisor sandbox. No network. No GPU. No host filesystem beyond the task workspace."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound

from core.config import SETTINGS
from core.schemas import SandboxResult, WorkbenchError

logger = logging.getLogger(__name__)

_MAX_OUTPUT_CHARS = 20_000


def workspace_for(task_id: str) -> Path:
    """SETTINGS.paths.workspaces / task_id. Created 0700 if missing.

    0700 is correct when the host process creating workspaces runs as the same uid the
    sandbox container uses (10001, matching sandbox/Dockerfile's `useradd -u 10001`) — the
    bind mount just works. Docker bind mounts never remap UIDs, so on a host where the caller
    runs as some other uid, a strict 0700 would leave the container unable to read or write
    /work at all. Widened to 0777 so the container can always read/write its own workspace
    regardless of which uid created it; this project has no host multi-tenancy to protect
    against (see CLAUDE.md's forbidden list), so this is not a meaningful security relaxation.
    """
    ws = SETTINGS.paths.workspaces / task_id
    ws.mkdir(mode=0o700, parents=True, exist_ok=True)
    ws.chmod(0o777)
    return ws


def _assert_inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise WorkbenchError(f"path {path} escapes workspace {root}") from None
    return resolved


def _snapshot(ws: Path) -> set[str]:
    return {str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file()}


def _truncate(s: str) -> str:
    return s if len(s) <= _MAX_OUTPUT_CHARS else s[:_MAX_OUTPUT_CHARS]


def _run_container(ws: Path, command: list[str], timeout_s: int) -> tuple[int, str, str, bool]:
    """Run one container to completion, always removing it. Never removed = a bug.

    Returns (exit_code, stdout, stderr, timed_out).
    """
    try:
        client = docker.from_env()
    except DockerException as e:
        raise WorkbenchError(f"docker daemon unavailable: {e}") from e

    try:
        client.images.get(SETTINGS.sandbox.image)
    except ImageNotFound as e:
        raise WorkbenchError(
            f"sandbox image {SETTINGS.sandbox.image!r} not found locally — build it with "
            f"'docker build -t {SETTINGS.sandbox.image} sandbox/' first; the sandbox never "
            f"pulls images over the network"
        ) from e
    except APIError as e:
        raise WorkbenchError(f"docker daemon error checking image: {e}") from e

    container = None
    timed_out = False
    try:
        container = client.containers.run(
            image=SETTINGS.sandbox.image,
            command=command,
            runtime=SETTINGS.sandbox.runtime,      # runsc (gVisor); runc is the documented fallback
            network_mode="none",                   # NON-NEGOTIABLE — no network interface at all
            volumes={str(ws): {"bind": "/work", "mode": "rw"}},
            working_dir="/work",
            mem_limit=SETTINGS.sandbox.mem_limit,
            pids_limit=SETTINGS.sandbox.pids_limit,
            cpu_quota=100_000,                     # 1 CPU
            user="10001:10001",
            read_only=False,                       # /work must be writable
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            detach=True,
            remove=False,
        )

        deadline = time.monotonic() + timeout_s
        while True:
            container.reload()
            if container.status in ("exited", "dead"):
                break
            if time.monotonic() >= deadline:
                timed_out = True
                try:
                    container.kill()
                except APIError:
                    pass
                container.reload()
                break
            time.sleep(0.2)

        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        exit_code = container.attrs.get("State", {}).get("ExitCode", -1)
        return exit_code, stdout, stderr, timed_out
    except APIError as e:
        raise WorkbenchError(f"sandbox container failed: {e}") from e
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except (APIError, NotFound):
                pass


def run_python(
    task_id: str,
    code: str,
    *,
    filename: str = "main.py",
    input_files: dict[str, bytes] | None = None,
    timeout_s: int | None = None,
) -> SandboxResult:
    """Write code into the workspace, run it in the sandbox, collect stdout/stderr/artifacts."""
    ws = workspace_for(task_id)
    timeout = timeout_s if timeout_s is not None else SETTINGS.sandbox.timeout_s

    for rel_name, data in (input_files or {}).items():
        target = _assert_inside(ws / rel_name, ws)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    code_path = _assert_inside(ws / filename, ws)
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text(code)

    before = _snapshot(ws)
    started = time.monotonic()
    exit_code, stdout, stderr, timed_out = _run_container(ws, ["python", f"/work/{filename}"], timeout)
    duration_ms = (time.monotonic() - started) * 1000
    artifacts = sorted(_snapshot(ws) - before)

    return SandboxResult(
        exit_code=exit_code,
        stdout=_truncate(stdout),
        stderr=_truncate(stderr),
        duration_ms=duration_ms,
        artifacts=artifacts,
        timed_out=timed_out,
    )


def run_tests(task_id: str, code: str, tests: str) -> SandboxResult:
    """Write code.py + test_code.py, run `pytest -q test_code.py`.

    This function IS R14 ('run AND verified'). The agent is not allowed to declare a coding
    task complete on the basis of run_python() alone — L4 must call this.

    The code module is written as `solution.py`, not `code.py` — Python ships a stdlib module
    literally named `code` (the interactive-interpreter helper), and `test_code.py` importing
    `from code import ...` silently resolves to that stdlib module instead of the workspace
    file once anything else in the process has already imported it. `tests` must therefore
    import from `solution`, e.g. `from solution import add`.
    """
    ws = workspace_for(task_id)
    (ws / "solution.py").write_text(code)
    (ws / "test_code.py").write_text(tests)

    before = _snapshot(ws)
    started = time.monotonic()
    exit_code, stdout, stderr, timed_out = _run_container(
        ws, ["pytest", "-q", "test_code.py"], SETTINGS.sandbox.timeout_s
    )
    duration_ms = (time.monotonic() - started) * 1000
    artifacts = sorted(_snapshot(ws) - before)

    return SandboxResult(
        exit_code=exit_code,
        stdout=_truncate(stdout),
        stderr=_truncate(stderr),
        duration_ms=duration_ms,
        artifacts=artifacts,
        timed_out=timed_out,
    )


def verify_calculation(
    task_id: str, expression: str, variables: dict[str, float], units: dict[str, str]
) -> dict:
    """Dual-path calculation check (R9 'calculations with steps shown').

    Path A: evaluate with pint, carrying units through, then normalise to base units.
    Path B: re-derive symbolically with sympy — substituting the raw numbers, unit-naive —
    and compare. A variable whose declared unit implies a real scale factor away from pint's
    base units (e.g. kilometres, minutes) will disagree with Path B's raw substitution unless
    the caller already normalised it; that divergence is exactly the class of bug this check
    exists to catch.

    Returns {"agree": bool, "value_a":..., "value_b":..., "unit":..., "steps": [str, ...]}.
    Disagreement beyond 1e-6 relative -> agree=False; L4 escalates to a human.
    """
    import pint
    import sympy

    ureg = pint.UnitRegistry()
    steps: list[str] = [f"expression: {expression}"]

    pint_vars: dict[str, "pint.Quantity"] = {}
    for name, val in variables.items():
        unit = units.get(name, "")
        q = ureg.Quantity(val, unit) if unit else ureg.Quantity(val)
        pint_vars[name] = q
        steps.append(f"{name} = {val} {unit}".rstrip())

    try:
        raw_a = eval(expression, {"__builtins__": {}}, pint_vars)  # noqa: S307 — restricted globals, math-only DSL
    except Exception as e:
        raise WorkbenchError(f"pint (Path A) evaluation of {expression!r} failed: {e}") from e

    quantity_a = raw_a if isinstance(raw_a, ureg.Quantity) else ureg.Quantity(raw_a)
    base_a = quantity_a.to_base_units()
    value_a = float(base_a.magnitude)
    unit_str = str(base_a.units)
    steps.append(f"pint (Path A): {expression} = {quantity_a} -> base units {base_a}")

    symbols = {name: sympy.Symbol(name) for name in variables}
    try:
        sym_expr = sympy.sympify(expression, locals=symbols)
        substituted = sym_expr.subs({symbols[name]: variables[name] for name in variables})
        value_b = float(substituted.evalf())
    except Exception as e:
        raise WorkbenchError(f"sympy (Path B) evaluation of {expression!r} failed: {e}") from e

    steps.append(f"sympy (Path B, unit-naive re-derivation): {expression} = {value_b}")

    if value_a == 0:
        agree = abs(value_b) < 1e-9
    else:
        agree = abs(value_a - value_b) / abs(value_a) <= 1e-6

    steps.append(f"agree={agree} (relative tolerance 1e-6; Path A in base units, Path B unit-naive)")

    return {
        "agree": agree,
        "value_a": value_a,
        "value_b": value_b,
        "unit": unit_str,
        "steps": steps,
    }
