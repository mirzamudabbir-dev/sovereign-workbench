"""L8 — tests for sovereignty receipts.

Non-integration tests never need a real Tetragon/pktap capture running — they point
whichever egress source this environment is configured for (SETTINGS.audit.egress_source;
see core/config.py's AuditCfg) at a throwaway synthetic log file, so the same test suite
is profile-agnostic across the venue box (tetragon) and this dev machine (pktap), same
pattern as tests/test_router.py and tests/test_serving.py use for their dual model
profiles. Only the two @pytest.mark.integration tests need a live capture process.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import core.receipt as receipt_module
from core.config import SETTINGS
from core.receipt import (
    _canonical_payload,
    build_receipt,
    is_external,
    read_egress,
    verify,
    write_receipt,
)
from core.schemas import Modality, RouteDecision, ToolCall, WorkbenchError

# ─────────────────────────── fixtures ───────────────────────────────────────────────


@pytest.fixture
def egress_log(tmp_path, monkeypatch):
    """Redirects whichever egress source this environment is configured for
    (SETTINGS.audit.egress_source) at a throwaway file, without touching the other
    source's entry. Returns (log_path, source_name)."""
    source = SETTINGS.audit.egress_source
    log_path = tmp_path / "events.json"
    _, parse_fn = receipt_module._SOURCES[source]
    monkeypatch.setitem(receipt_module._SOURCES, source, (log_path, parse_fn))
    return log_path, source


def _event_line(source: str, ts: datetime, binary: str, pid: int, daddr: str, dport: int, blocked: bool = False) -> str:
    import json

    if source == "tetragon":
        action = "KPROBE_ACTION_SIGKILL" if blocked else "KPROBE_ACTION_POST"
        obj = {
            "process_kprobe": {
                "process": {"binary": binary, "pid": pid},
                "function_name": "tcp_connect",
                "args": [{"sock_arg": {"daddr": daddr, "dport": dport}}],
                "action": action,
            },
            "time": ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    else:  # pktap
        obj = {
            "timestamp": ts.isoformat(),
            "binary": binary,
            "pid": pid,
            "destination_ip": daddr,
            "destination_port": dport,
            "action": "blocked" if blocked else "observed",
        }
    return json.dumps(obj)


def _write_events(log_path: Path, source: str, events: list[tuple]) -> None:
    lines = [_event_line(source, *e) for e in events]
    log_path.write_text("\n".join(lines) + "\n")


def _sample_route_decision(reason: str = "only capable model") -> RouteDecision:
    return RouteDecision(
        step_id="t1.s1", required_modalities=[Modality.TEXT], estimated_tokens=100,
        needs_structured_output=False, candidates_considered=["gemma4-e2b"], rejected={},
        chosen_model="gemma4-e2b", reason=reason, latency_ms=12.3,
    )


def _sample_tool_call(started_at: datetime) -> ToolCall:
    return ToolCall(
        call_id="c1", step_id="t1.s1", tool_name="kb.search", args_sha256="deadbeef",
        started_at=started_at, duration_ms=5.0, ok=True, error=None,
    )


# ─────────────────────────── is_external ────────────────────────────────────────────


@pytest.mark.parametrize(
    "ip,expected",
    [
        ("127.0.0.1", False), ("127.255.255.255", False),
        ("10.0.0.1", False), ("10.255.255.255", False),
        ("172.16.0.1", False), ("172.31.255.255", False),
        ("172.15.255.255", True), ("172.32.0.1", True),
        ("192.168.0.1", False), ("192.168.255.255", False),
        ("169.254.1.1", False),          # link-local
        ("224.0.0.1", False),            # multicast
        ("0.0.0.0", False),              # unspecified
        ("8.8.8.8", True),
        ("1.1.1.1", True),
        ("93.184.216.34", True),
        ("::1", False),                  # IPv6 loopback
        ("fe80::1", False),              # IPv6 link-local
        ("fc00::1", False),              # IPv6 unique-local
        ("ff02::1", False),              # IPv6 multicast
        ("2001:4860:4860::8888", True),  # public IPv6
        ("not-an-ip", True),             # unparseable -> fail closed as external
    ],
)
def test_is_external_table(ip, expected):
    assert is_external(ip) is expected


# ─────────────────────────── canonicalisation ───────────────────────────────────────


def test_canonical_payload_is_deterministic():
    started = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(minutes=5)
    fields = {
        "task_id": "t-determinism",
        "started_at": started,
        "finished_at": finished,
        "model_manifests": {"gemma4-e2b": "abc123"},
        "route_decisions": [_sample_route_decision()],
        "tool_trace": [_sample_tool_call(started)],
        "egress_events": [],
        "external_egress_count": 0,
        "artifact_hashes": {"note.docx": "deadbeef"},
    }
    payload_a = _canonical_payload(fields)
    payload_b = _canonical_payload(dict(fields))  # a fresh dict, same content, different key order in memory
    assert payload_a == payload_b


# ─────────────────────────── read_egress ────────────────────────────────────────────


def test_missing_tetragon_log_raises(egress_log):
    log_path, _source = egress_log
    assert not log_path.exists()
    with pytest.raises(WorkbenchError, match="not found"):
        read_egress(datetime.now(timezone.utc), datetime.now(timezone.utc))


def test_missing_tetragon_log_raises_even_when_empty(egress_log):
    log_path, _source = egress_log
    log_path.write_text("")
    with pytest.raises(WorkbenchError, match="empty"):
        read_egress(datetime.now(timezone.utc), datetime.now(timezone.utc))


def test_read_egress_filters_by_time_window(egress_log):
    log_path, source = egress_log
    t0 = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    _write_events(
        log_path, source,
        [
            (t0 - timedelta(hours=1), "curl", 1, "8.8.8.8", 443, False),  # outside window
            (t0, "qdrant-client", 2, "127.0.0.1", 6333, False),           # inside window
            (t0 + timedelta(hours=1), "curl", 3, "1.1.1.1", 443, False),  # outside window
        ],
    )
    events = read_egress(t0 - timedelta(seconds=1), t0 + timedelta(seconds=1))
    assert len(events) == 1
    assert events[0].destination_ip == "127.0.0.1"


# ─────────────────────────── sign / verify ──────────────────────────────────────────


def test_sign_then_verify_roundtrip(egress_log):
    log_path, source = egress_log
    started = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(minutes=1)
    _write_events(log_path, source, [(started + timedelta(seconds=1), "qdrant-client", 1, "127.0.0.1", 6333, False)])

    receipt = build_receipt(
        "t-roundtrip", started, finished, [_sample_route_decision()], [_sample_tool_call(started)], []
    )
    ok, problems = verify(receipt)
    assert ok is True
    assert problems == []
    assert receipt.external_egress_count == 0


def test_external_event_sets_count_and_fails_verify(egress_log):
    log_path, source = egress_log
    started = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(minutes=1)
    _write_events(log_path, source, [(started + timedelta(seconds=1), "curl", 1, "8.8.8.8", 443, False)])

    receipt = build_receipt(
        "t-external", started, finished, [_sample_route_decision()], [_sample_tool_call(started)], []
    )
    assert receipt.external_egress_count == 1

    ok, problems = verify(receipt)
    assert ok is False
    assert any("external_egress_count" in p for p in problems)


def test_tampered_field_fails_verification(egress_log):
    log_path, source = egress_log
    started = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(minutes=1)
    _write_events(log_path, source, [(started + timedelta(seconds=1), "qdrant-client", 1, "127.0.0.1", 6333, False)])

    receipt = build_receipt(
        "t-tamper", started, finished, [_sample_route_decision()], [_sample_tool_call(started)], []
    )
    tampered = receipt.model_copy(deep=True)
    tampered.route_decisions[0].reason = tampered.route_decisions[0].reason[:-1] + "X"  # flip one char

    ok, problems = verify(tampered)
    assert ok is False
    assert any("hash" in p or "signature" in p for p in problems)


def test_tampered_artifact_hash_fails(egress_log, tmp_path, monkeypatch):
    log_path, source = egress_log
    started = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(minutes=1)
    _write_events(log_path, source, [(started + timedelta(seconds=1), "qdrant-client", 1, "127.0.0.1", 6333, False)])

    # verify() re-hashes artifacts at SETTINGS.paths.outputs/<task_id>/<filename> — the
    # same convention core.render.render() actually writes to — since artifact_hashes
    # (a frozen contracts field) stores only a bare filename, not a full path.
    outputs_dir = tmp_path / "outputs"
    monkeypatch.setattr(SETTINGS.paths, "outputs", outputs_dir)
    task_dir = outputs_dir / "t-artifact"
    task_dir.mkdir(parents=True)
    artifact = task_dir / "note.docx"
    artifact.write_bytes(b"original content")

    receipt = build_receipt(
        "t-artifact", started, finished, [_sample_route_decision()], [_sample_tool_call(started)], [artifact]
    )
    ok, problems = verify(receipt)
    assert ok is True, problems  # unmodified: clean

    artifact.write_bytes(b"tampered content - completely different bytes")
    ok2, problems2 = verify(receipt)
    assert ok2 is False
    assert any("note.docx" in p for p in problems2)


def test_receipt_json_is_stable_across_runs(egress_log):
    """Building a receipt for the identical inputs twice produces byte-identical
    payload hashes both times — the whole point of a deterministic canonical form."""
    log_path, source = egress_log
    started = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(minutes=1)
    _write_events(log_path, source, [(started + timedelta(seconds=1), "qdrant-client", 1, "127.0.0.1", 6333, False)])

    receipt_a = build_receipt(
        "t-stable", started, finished, [_sample_route_decision()], [_sample_tool_call(started)], []
    )
    receipt_b = build_receipt(
        "t-stable", started, finished, [_sample_route_decision()], [_sample_tool_call(started)], []
    )
    assert receipt_a.payload_sha256 == receipt_b.payload_sha256


def test_write_receipt_roundtrips_through_json(egress_log, tmp_path, monkeypatch):
    log_path, source = egress_log
    monkeypatch.setattr(SETTINGS.paths, "receipts", tmp_path / "receipts")
    started = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(minutes=1)
    _write_events(log_path, source, [(started + timedelta(seconds=1), "qdrant-client", 1, "127.0.0.1", 6333, False)])

    receipt = build_receipt(
        "t-write", started, finished, [_sample_route_decision()], [_sample_tool_call(started)], []
    )
    out_path = write_receipt(receipt)
    assert out_path.is_file()
    assert out_path.name == "t-write.receipt.json"

    from core.schemas import TaskReceipt

    reloaded = TaskReceipt.model_validate_json(out_path.read_text())
    ok, problems = verify(reloaded)
    assert ok is True, problems


# ─────────────────────────── integration (needs a live capture) ────────────────────


@pytest.mark.integration
def test_live_capture_sees_internal_connections():
    """A real Qdrant call (127.0.0.1:6333) should appear in the live egress log as an
    internal event within a tight time window around the call."""
    from core.kb import stats

    started = datetime.now(timezone.utc)
    stats()  # any real call to the live Qdrant on 127.0.0.1:6333
    finished = datetime.now(timezone.utc)

    events = read_egress(started - timedelta(seconds=2), finished + timedelta(seconds=2))
    assert any(e.destination_ip == "127.0.0.1" and not e.is_external for e in events)


@pytest.mark.integration
def test_negative_control_produces_external_event():
    """Requires the ENFORCEMENT policy loaded (see scripts/negative_control.sh) and a
    live capture — deliberately triggers an outbound connection and expects the
    monitor to have recorded it as external (and, under enforcement, blocked)."""
    import subprocess

    started = datetime.now(timezone.utc)
    subprocess.run(["curl", "-m", "3", "https://example.com"], capture_output=True)
    finished = datetime.now(timezone.utc)

    events = read_egress(started - timedelta(seconds=2), finished + timedelta(seconds=2))
    assert any(e.is_external for e in events)
