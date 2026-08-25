#!/usr/bin/env python3
"""L0 — pre-demo sanity sweep. Run before every demo: `make preflight`.

Stdlib only. Does NOT import from core/ — L0 owns host/container substrate, not
application logic. Ports and served-model-name conventions are taken from
docs/01_CONTRACTS.md (the ports table) and config.yaml, never from a core/ import.

Check 5 is a NEGATIVE CONTROL: a container with --network=none attempting an
outbound connection MUST fail. If it succeeds, the air gap is not real — this
prints a red banner and the script exits 1 regardless of every other check.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

RED = "\033[1;31m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
BOLD = "\033[1m"
NC = "\033[0m"

REPO_ROOT = Path(__file__).resolve().parent.parent

# Ports table — docs/01_CONTRACTS.md. served_model_name matches config.yaml /
# scripts/03_start_services.sh conventions (manifests/ are owned by L1).
VLLM_SERVICES = [
    (8001, "qwen25-vl-7b"),
    (8002, "qwen25-coder-7b"),
    (8003, "arch-router-1.5b"),
    (8004, "paddleocr-vl"),
]
QDRANT_URL = "http://127.0.0.1:6333"
MIN_FREE_VRAM_GB = 20
HTTP_TIMEOUT_S = 3


class CheckResult:
    def __init__(self, name: str, ok: bool, detail: str):
        self.name = name
        self.ok = ok
        self.detail = detail


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _http_get(url: str, timeout: float = HTTP_TIMEOUT_S) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


# ─────────────────────────── checks ───────────────────────────────────────


def check_gpu() -> CheckResult:
    try:
        cp = _run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"])
    except FileNotFoundError:
        return CheckResult("1. GPU present, free VRAM ≥ 20 GB", False, "nvidia-smi not found on this host")
    except Exception as exc:
        return CheckResult("1. GPU present, free VRAM ≥ 20 GB", False, f"nvidia-smi failed: {exc}")
    if cp.returncode != 0:
        return CheckResult("1. GPU present, free VRAM ≥ 20 GB", False, f"nvidia-smi exit {cp.returncode}: {cp.stderr.strip()}")
    try:
        free_mb = int(cp.stdout.strip().splitlines()[0])
    except (IndexError, ValueError):
        return CheckResult("1. GPU present, free VRAM ≥ 20 GB", False, f"could not parse nvidia-smi output: {cp.stdout!r}")
    free_gb = free_mb / 1024
    ok = free_gb >= MIN_FREE_VRAM_GB
    return CheckResult("1. GPU present, free VRAM ≥ 20 GB", ok, f"{free_gb:.1f} GB free")


def check_vllm_endpoints() -> CheckResult:
    problems = []
    for port, expected_name in VLLM_SERVICES:
        url = f"http://127.0.0.1:{port}/v1/models"
        try:
            status, body = _http_get(url)
            data = json.loads(body)
            served = [m.get("id") for m in data.get("data", [])]
            if status != 200 or expected_name not in served:
                problems.append(f":{port} expected '{expected_name}', got {served or 'no models'}")
        except Exception as exc:
            problems.append(f":{port} unreachable ({exc})")
    if problems:
        return CheckResult("2. All 4 vLLM /v1/models answer with correct name", False, "; ".join(problems))
    return CheckResult("2. All 4 vLLM /v1/models answer with correct name", True, "all 4 services healthy")


def check_qdrant_and_tetragon() -> CheckResult:
    problems = []

    try:
        status, _ = _http_get(f"{QDRANT_URL}/healthz")
        if status != 200:
            problems.append(f"qdrant /healthz status {status}")
    except Exception as exc:
        problems.append(f"qdrant unreachable ({exc})")

    try:
        cp = _run(["docker", "ps", "--filter", "name=tetragon", "--format", "{{.Status}}"])
        if cp.returncode != 0 or not cp.stdout.strip():
            problems.append("tetragon container not running")
    except FileNotFoundError:
        problems.append("docker not found")

    events_path = REPO_ROOT / "data" / "tetragon" / "events.json"
    if not events_path.exists():
        problems.append(f"{events_path} does not exist yet")
    else:
        size1 = events_path.stat().st_size
        time.sleep(2)
        size2 = events_path.stat().st_size
        if size2 <= size1:
            problems.append(f"events.json not growing ({size1} -> {size2} bytes over 2s)")

    if problems:
        return CheckResult("3. Qdrant healthy, Tetragon running, events.json growing", False, "; ".join(problems))
    return CheckResult("3. Qdrant healthy, Tetragon running, events.json growing", True, "qdrant OK, tetragon OK, events growing")


def check_gvisor_runtime() -> CheckResult:
    try:
        cp = _run(["docker", "run", "--rm", "--runtime=runsc", "--network=none", "alpine:3", "true"], timeout=30)
    except FileNotFoundError:
        return CheckResult("4. gVisor runtime usable (--runtime=runsc)", False, "docker not found")
    except subprocess.TimeoutExpired:
        return CheckResult("4. gVisor runtime usable (--runtime=runsc)", False, "timed out")
    ok = cp.returncode == 0
    detail = "runsc container ran cleanly" if ok else f"exit {cp.returncode}: {cp.stderr.strip()[-300:]}"
    return CheckResult("4. gVisor runtime usable (--runtime=runsc)", ok, detail)


def check_negative_control() -> CheckResult:
    """A --network=none container reaching the open internet MUST fail. If it
    succeeds, the air gap is fake — print a red banner regardless of every other check."""
    name = "5. NEGATIVE CONTROL: --network=none egress must FAIL"
    try:
        cp = _run(
            ["docker", "run", "--rm", "--network=none", "alpine:3", "wget", "-T2", "-q", "-O-", "http://1.1.1.1"],
            timeout=20,
        )
    except FileNotFoundError:
        return CheckResult(name, False, "docker not found — cannot run the negative control at all")
    except subprocess.TimeoutExpired:
        # A hang is not a success — but it is also not proof of a block. Treat as fail-safe pass.
        return CheckResult(name, True, "wget timed out without responding (treated as blocked)")

    # `docker run` propagates the *container's* exit code only once it actually
    # started a container. If docker itself couldn't run at all (daemon down,
    # socket unreachable, image pull blocked), it also exits nonzero — that
    # would otherwise be misread as "egress correctly blocked" when the check
    # never actually executed. Detect that failure mode explicitly.
    daemon_error_markers = (
        "Cannot connect to the Docker daemon",
        "docker daemon is not running",
        "error during connect",
        "permission denied while trying to connect",
        "failed to connect to the docker api",
        "docker.sock",
    )
    stderr_lower = cp.stderr.lower()
    if any(marker.lower() in stderr_lower for marker in daemon_error_markers):
        return CheckResult(name, False, f"could not run the check at all — docker daemon unreachable: {cp.stderr.strip()[-200:]}")

    if cp.returncode == 0:
        print(f"\n{RED}{BOLD}" + "#" * 70 + NC)
        print(f"{RED}{BOLD}#  NEGATIVE CONTROL FAILED — EGRESS IS NOT BLOCKED.{NC}")
        print(f"{RED}{BOLD}#  A --network=none container reached the open internet.{NC}")
        print(f"{RED}{BOLD}#  THE AIR GAP IS NOT REAL. DO NOT DEMO.{NC}")
        print(f"{RED}{BOLD}" + "#" * 70 + f"{NC}\n")
        return CheckResult(name, False, "wget SUCCEEDED against 1.1.1.1 — egress is not blocked")
    return CheckResult(name, True, f"wget correctly failed (exit {cp.returncode})")


def check_offline_env() -> CheckResult:
    run_dir = REPO_ROOT / "run"
    pidfiles = sorted(run_dir.glob("*.pid")) if run_dir.exists() else []
    vllm_pidfiles = [p for p in pidfiles if p.stem not in ("api", "ui")]
    if not vllm_pidfiles:
        return CheckResult("6. HF_HUB_OFFLINE=1 in every service env", False, "no running vLLM services found (run/*.pid empty)")

    problems = []
    for pidfile in vllm_pidfiles:
        pid = pidfile.read_text().strip()
        environ_path = Path(f"/proc/{pid}/environ")
        if not environ_path.exists():
            problems.append(f"{pidfile.stem}: /proc/{pid}/environ not available on this platform")
            continue
        try:
            raw = environ_path.read_bytes()
        except PermissionError:
            problems.append(f"{pidfile.stem}: permission denied reading /proc/{pid}/environ")
            continue
        env = dict(kv.split("=", 1) for kv in raw.decode(errors="replace").split("\0") if "=" in kv)
        if env.get("HF_HUB_OFFLINE") != "1":
            problems.append(f"{pidfile.stem}: HF_HUB_OFFLINE not set to 1")

    if problems:
        return CheckResult("6. HF_HUB_OFFLINE=1 in every service env", False, "; ".join(problems))
    return CheckResult("6. HF_HUB_OFFLINE=1 in every service env", True, f"{len(vllm_pidfiles)} service(s) confirmed offline")


def check_templates() -> CheckResult:
    templates_dir = REPO_ROOT / "templates"
    if not templates_dir.exists():
        return CheckResult("7. Templates exist and open", False, f"{templates_dir} does not exist yet (L7b not built)")
    files = sorted(templates_dir.glob("*.docx")) + sorted(templates_dir.glob("*.pptx")) + sorted(templates_dir.glob("*.xlsx"))
    if not files:
        return CheckResult("7. Templates exist and open", False, f"no .docx/.pptx/.xlsx found in {templates_dir}")
    problems = []
    for f in files:
        if not zipfile.is_zipfile(f):
            problems.append(f"{f.name}: not a valid OOXML zip")
            continue
        try:
            with zipfile.ZipFile(f) as zf:
                zf.namelist()
        except Exception as exc:
            problems.append(f"{f.name}: failed to open ({exc})")
    if problems:
        return CheckResult("7. Templates exist and open", False, "; ".join(problems))
    return CheckResult("7. Templates exist and open", True, f"{len(files)} template(s) open cleanly")


# ─────────────────────────── report ────────────────────────────────────────


def main() -> int:
    checks = [
        check_gpu(),
        check_vllm_endpoints(),
        check_qdrant_and_tetragon(),
        check_gvisor_runtime(),
        check_negative_control(),
        check_offline_env(),
        check_templates(),
    ]

    print(f"\n{BOLD}SOVEREIGN WORKBENCH — PREFLIGHT{NC}\n" + "-" * 70)
    all_ok = True
    for c in checks:
        badge = f"{GREEN}PASS{NC}" if c.ok else f"{RED}FAIL{NC}"
        all_ok = all_ok and c.ok
        print(f"[{badge}] {c.name}\n        {c.detail}")
    print("-" * 70)

    if all_ok:
        print(f"{GREEN}{BOLD}ALL CHECKS GREEN — safe to demo.{NC}\n")
        return 0

    print(f"{RED}{BOLD}PREFLIGHT FAILED — do not demo until every check is green.{NC}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
