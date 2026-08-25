# L5 — TOOL & SANDBOX PLANE

## MISSION LOCK

**Build:** a gVisor-isolated, network-less code execution sandbox, and the four local tools the
PS names: file read/write, code execution, spreadsheet work, document search.

**You are NOT building:** the agent that decides *when* to call tools (L4), the KB itself (L6),
or any LLM interaction. `kb.search` is a thin delegate to `core.kb` — you do not implement retrieval.

**Serves:** R6 (local tools), R14 (coding task run **and verified** in a sandbox), R1.

**Files You Own:**
```
core/sandbox.py
core/tools.py
sandbox/Dockerfile
sandbox/requirements.txt
tests/test_sandbox.py
```

---

## The two properties that matter

1. **`network_mode="none"`** — the container gets no network interface at all, not a blocked
   one. This is what makes "the agent cannot exfiltrate" true by construction rather than by
   policy. It is a bigger deal than the runtime choice and must never be removed.
2. **`runtime="runsc"`** — gVisor. Syscalls are intercepted by a userspace kernel, so a
   container escape does not reach the host kernel. Read from `SETTINGS.sandbox.runtime` so the
   `runc` fallback works without a code change.

**gVisor blocks PCIe passthrough, so the sandbox has no GPU. That is intentional.** The sandbox
runs pandas, openpyxl and pytest — never inference. Do not add `device_requests`. Do not
propose Firecracker to regain GPU access; nothing in the sandbox needs it.

---

## `sandbox/Dockerfile`

```dockerfile
FROM python:3.11-slim
RUN useradd -u 10001 -m runner
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
USER runner
WORKDIR /work
CMD ["python", "/work/main.py"]
```

`sandbox/requirements.txt` — deliberately minimal, no network libs:
```
pandas==2.2.3
numpy==2.2.1
openpyxl==3.1.5
pint==0.24.4          # unit-aware calculations (R9: "calculations with steps shown")
sympy==1.13.3         # independent re-derivation for the verify path
pytest==8.3.4
```

**Do not add `requests`, `httpx`, `urllib3`, or any HTTP client.** If a generated script imports
one it must fail loudly — that failure is a feature.

---

## `core/sandbox.py` — required API

```python
"""L5 — gVisor sandbox. No network. No GPU. No host filesystem beyond the task workspace."""

def workspace_for(task_id: str) -> Path:
    """SETTINGS.paths.workspaces / task_id. Created 0700 if missing."""


def run_python(
    task_id: str,
    code: str,
    *,
    filename: str = "main.py",
    input_files: dict[str, bytes] | None = None,
    timeout_s: int | None = None,
) -> SandboxResult:
    """Write code into the workspace, run it in the sandbox, collect stdout/stderr/artifacts.

    docker.from_env().containers.run(
        image=SETTINGS.sandbox.image,
        command=["python", f"/work/{filename}"],
        runtime=SETTINGS.sandbox.runtime,      # runsc
        network_mode="none",                   # NON-NEGOTIABLE
        volumes={str(ws): {"bind": "/work", "mode": "rw"}},
        working_dir="/work",
        mem_limit=SETTINGS.sandbox.mem_limit,
        pids_limit=SETTINGS.sandbox.pids_limit,
        cpu_quota=100_000,                     # 1 CPU
        user="10001:10001",
        read_only=False,                       # /work must be writable
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        detach=True, remove=False,
    )

    Wait with timeout; on timeout kill the container and set timed_out=True.
    ALWAYS remove the container in a finally block.
    Truncate stdout/stderr to 20_000 chars each.
    artifacts = files in the workspace that did not exist before the run.
    """


def run_tests(task_id: str, code: str, tests: str) -> SandboxResult:
    """Write code.py + test_code.py, run `pytest -q test_code.py`.

    This function IS R14 ('run AND verified'). The agent is not allowed to declare a coding
    task complete on the basis of run_python() alone — L4 must call this.
    """


def verify_calculation(task_id: str, expression: str, variables: dict[str, float],
                       units: dict[str, str]) -> dict:
    """Dual-path calculation check (R9 'calculations with steps shown').

    Path A: evaluate with pint, carrying units through.
    Path B: re-derive symbolically with sympy, substitute, compare.
    Returns {"agree": bool, "value_a":..., "value_b":..., "unit":..., "steps": [str, ...]}.
    'steps' is the human-readable derivation rendered into the deliverable.
    Disagreement beyond 1e-6 relative -> agree=False; L4 escalates to a human.
    """
```

---

## `core/tools.py` — the four PS-named tools

```python
"""L5 — the local tool surface. Exactly four families. Do not add a fifth."""

TOOL_REGISTRY: dict[str, Callable] = {
    "fs.read":     fs_read,
    "fs.write":    fs_write,
    "code.exec":   code_exec,
    "code.test":   code_test,
    "sheet.read":  sheet_read,
    "sheet.write": sheet_write,
    "kb.search":   kb_search,      # delegates to core.kb.search — do not implement retrieval
}

def call_tool(task_id: str, step_id: str, name: str, args: dict) -> tuple[Any, ToolCall]:
    """Single entry point. Validates the name, times the call, hashes args, builds the
    ToolCall record for the L8 receipt, and re-raises WorkbenchError on failure."""
```

Guarantees every tool must uphold:
- **Path jail:** every path argument is resolved and asserted to be inside
  `workspace_for(task_id)` or `SETTINGS.paths.uploads` (read-only). A path escaping either is
  `WorkbenchError`, not a silent clamp. Write `test_path_traversal_blocked`.
- **Write confirmation:** `fs.write` and `sheet.write` outside the task workspace return
  `requires_approval=True` instead of writing. L4 surfaces this to the human.
- **Every call returns a `ToolCall`** with `args_sha256`, duration and ok/error. L8 needs all of them.

---

## Tests — `tests/test_sandbox.py`

```python
@pytest.mark.integration
def test_hello_world_runs()
def test_network_is_unreachable()          # socket.create_connection -> exception in stdout
def test_import_requests_fails()           # not installed, by design
def test_timeout_kills_container()
def test_container_always_removed()        # no orphans after a failing run
def test_runtime_is_runsc_or_documented_fallback()
def test_run_tests_reports_pytest_failure()
def test_verify_calculation_agrees_on_simple_case()
def test_verify_calculation_flags_unit_mismatch()

def test_path_traversal_blocked()          # "../../etc/passwd" -> WorkbenchError
def test_write_outside_workspace_requires_approval()
def test_call_tool_returns_toolcall_record()
```

`test_network_is_unreachable` is the one you will demo. It should run this inside the sandbox:
```python
import socket
try:
    socket.create_connection(("1.1.1.1", 80), timeout=2); print("REACHED")
except Exception as e:
    print("BLOCKED:", type(e).__name__)
```
and assert `"BLOCKED"` in stdout. Keep it as a named test so you can run it on stage.

---

## Definition of Done

```bash
docker build -t sovereign-sandbox:latest sandbox/
pytest tests/test_sandbox.py -v          # all pass, including network + traversal tests
docker ps -a | grep sovereign-sandbox    # → empty (no orphaned containers)
```

## Drift tripwires

- ❌ Adding network access "just for pip". Bake dependencies into the image.
- ❌ Giving the sandbox a GPU, or switching to Firecracker to get one.
- ❌ Adding a fifth tool family, an MCP server, or a plugin system.
- ❌ Implementing retrieval inside `kb.search`. Delegate to `core.kb`.
- ❌ `subprocess.run` on the host as a "simpler sandbox". The isolation is the point.
- ❌ Swallowing container errors. Every failure surfaces as a `WorkbenchError` or a non-zero
  `SandboxResult.exit_code`.

## Session exit

`PROGRESS.md`: runtime actually in use (`runsc` vs `runc`), sandbox image size,
observed cold-start latency, whether all tests pass.
`## Next action: L3 — core/ingest.py (PaddleOCR-VL + Docling → EvidenceSpans)`
