"""L8 — sovereignty receipts. Observes; never participates.

Reads whatever the host's kernel-level egress monitor already logged, signs a canonical
snapshot of the task, and writes a receipt an auditor can verify offline, on another
machine, without trusting this application's code. This module never calls out, never
starts a task, never retries anything — it only reads a log file and a signing key.

Egress source is dual, per SETTINGS.audit.egress_source (see core/config.py's AuditCfg,
added in PATCH_02 anticipating exactly this need):
  "tetragon" — the real target: Cilium Tetragon's JSONL export of tcp_connect kprobe
               events, produced by the tetragon container docker-compose.yml (L0) starts.
               This is what docs/L8_AUDIT.md's TETRAGON_LOG constant assumes.
  "pktap"    — this dev machine's substitute. macOS has no Tetragon (no eBPF); a future
               L0-owned capture process is expected to tail Apple's pktap kernel packet
               tap (DLT_PKTAP, kernel-level like Tetragon's kprobe — not an app-level log
               shipper) and append one JSON object per connection, already shaped like
               EgressEvent, to PKTAP_LOG. No such capture script exists in this repo yet
               (out of L8's "Files You Own" — see PROGRESS.md's Session 9 open questions);
               read_egress() is written and tested against that log shape regardless, so
               it needs no further change once L0 adds the producer.
Both paths converge on the same list[EgressEvent] and the same fail-closed rule: a
missing or empty log raises. A receipt with no monitor data is worse than no receipt.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel

from core.config import SETTINGS
from core.render import file_sha256
from core.schemas import EgressEvent, RouteDecision, TaskReceipt, ToolCall, WorkbenchError
from core.serving import REGISTRY

logger = logging.getLogger(__name__)

TETRAGON_LOG = SETTINGS.paths.data / "tetragon" / "events.json"
PKTAP_LOG = SETTINGS.paths.data / "pktap" / "events.json"

_SIGNING_KEY_PATH = SETTINGS.paths.data / "signing_key.pem"

# TaskReceipt fields that make up the signed payload. Deliberately excludes
# payload_sha256/signature_ed25519/public_key_ed25519 — those are OUTPUTS of signing
# this payload, so including them would be circular.
class _ReceiptPayload(BaseModel):
    """Every field of TaskReceipt except the three that are computed FROM this payload.
    _canonical_payload() always routes through this model — for both build_receipt's
    raw Python objects AND verify()'s already-JSON dicts (from
    `receipt.model_dump(mode="json")`) — specifically so the two call sites can never
    silently diverge on serialization. They did, once, in an earlier draft of this
    file: pydantic's mode="json" datetime output uses a trailing 'Z' (e.g. "...123Z")
    while plain `datetime.isoformat()` produces "+00:00" for the same instant — hand
    -serializing datetimes in one of the two call sites instead of always letting
    pydantic do it would have made every receipt fail its own signature check."""

    task_id: str
    started_at: datetime
    finished_at: datetime
    model_manifests: dict[str, str]
    route_decisions: list[RouteDecision]
    tool_trace: list[ToolCall]
    egress_events: list[EgressEvent]
    external_egress_count: int
    artifact_hashes: dict[str, str]


# ─────────────────────────── address classification ────────────────────────────────


def is_external(ip: str) -> bool:
    """False for loopback, RFC1918, link-local, multicast. True otherwise."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        # An address the monitor logged that isn't parseable is not something we can
        # clear as internal — treat it as external so it fails a receipt loudly rather
        # than silently passing an unrecognised value.
        return True
    return not (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


# ─────────────────────────── reading the kernel-level log ──────────────────────────


def _parse_tetragon_line(line: str) -> EgressEvent | None:
    """One line of Tetragon's JSON export. Only process_kprobe/tcp_connect events with a
    sock arg carry a destination; anything else on the export stream is skipped, not
    an error — Tetragon multiplexes many event kinds onto one export file."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("skipping malformed tetragon export line: %r", line[:200])
        return None

    kprobe = obj.get("process_kprobe")
    if not kprobe or kprobe.get("function_name") != "tcp_connect":
        return None

    sock_arg = next(
        (a["sock_arg"] for a in kprobe.get("args", []) if "sock_arg" in a), None
    )
    process = kprobe.get("process") or {}
    if sock_arg is None or "binary" not in process or "daddr" not in sock_arg:
        logger.warning("tetragon tcp_connect event missing expected fields: %r", obj)
        return None

    daddr = sock_arg["daddr"]
    action = "blocked" if "SIGKILL" in str(kprobe.get("action", "")) else "observed"
    return EgressEvent(
        timestamp=datetime.fromisoformat(obj["time"].replace("Z", "+00:00")),
        binary=process["binary"],
        pid=int(process.get("pid", -1)),
        destination_ip=daddr,
        destination_port=int(sock_arg.get("dport", 0)),
        action=action,
        is_external=is_external(daddr),
    )


def _parse_pktap_line(line: str) -> EgressEvent | None:
    """The pktap capture log's line shape is EgressEvent's own field names verbatim —
    see this module's docstring. `is_external` is still recomputed here rather than
    trusted from the log, so a capture script cannot mis-classify its own events."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("skipping malformed pktap capture line: %r", line[:200])
        return None
    try:
        return EgressEvent(
            timestamp=datetime.fromisoformat(obj["timestamp"]),
            binary=obj["binary"],
            pid=int(obj["pid"]),
            destination_ip=obj["destination_ip"],
            destination_port=int(obj["destination_port"]),
            action=obj.get("action", "observed"),
            is_external=is_external(obj["destination_ip"]),
        )
    except (KeyError, ValueError) as exc:
        logger.warning("pktap capture line missing/invalid field %s: %r", exc, line[:200])
        return None


_SOURCES = {"tetragon": (TETRAGON_LOG, _parse_tetragon_line), "pktap": (PKTAP_LOG, _parse_pktap_line)}


def read_egress(started_at: datetime, finished_at: datetime) -> list[EgressEvent]:
    """Tail the active egress log (SETTINGS.audit.egress_source), parse it, keep only
    tcp_connect events whose timestamp falls in [started_at, finished_at].

    If the log is missing or empty -> raise WorkbenchError. A receipt with no monitor
    data is WORSE than no receipt: it is an unverifiable claim. Never silently emit []
    because the file was absent — that is exactly the failure mode this function
    exists to catch. (A window with zero *matching* events, from a log that genuinely
    has content, is a legitimate empty result and is returned as [].)
    """
    source = SETTINGS.audit.egress_source
    log_path, parse_line = _SOURCES[source]

    if not log_path.is_file():
        raise WorkbenchError(
            f"egress monitor log not found at {log_path} (source={source!r}) — the "
            f"monitor is not running. A receipt cannot be built without it."
        )
    raw_lines = log_path.read_text(encoding="utf-8").splitlines()
    if not raw_lines:
        raise WorkbenchError(
            f"egress monitor log at {log_path} is empty (source={source!r}) — the "
            f"monitor produced no data at all. A receipt cannot be built without it."
        )

    events: list[EgressEvent] = []
    for line in raw_lines:
        if not line.strip():
            continue
        event = parse_line(line)
        if event is not None and started_at <= event.timestamp <= finished_at:
            events.append(event)
    return events


# ─────────────────────────── signing ────────────────────────────────────────────────


def _load_or_create_signing_key() -> Ed25519PrivateKey:
    if _SIGNING_KEY_PATH.is_file():
        return serialization.load_pem_private_key(_SIGNING_KEY_PATH.read_bytes(), password=None)

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _SIGNING_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SIGNING_KEY_PATH.write_bytes(pem)
    _SIGNING_KEY_PATH.chmod(0o600)
    logger.info("generated new receipt signing key at %s", _SIGNING_KEY_PATH)
    return key


def sign(payload: bytes) -> tuple[str, str]:
    """Ed25519 via cryptography. Private key at SETTINGS.paths.data/'signing_key.pem',
    generated on first use with mode 0600. Returns (signature_hex, public_key_hex)."""
    key = _load_or_create_signing_key()
    signature = key.sign(payload)
    public_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return signature.hex(), public_bytes.hex()


# ─────────────────────────── canonicalisation ───────────────────────────────────────


def _canonical_payload(receipt_fields: dict) -> bytes:
    """json.dumps(..., sort_keys=True, separators=(',',':')).encode() of the 9 payload
    fields — but ALWAYS after round-tripping them through _ReceiptPayload first (see
    its docstring for why: this is what keeps build_receipt and verify() byte-for-byte
    identical). Deterministic — verify_receipt must reproduce this byte-for-byte."""
    normalized = _ReceiptPayload(**receipt_fields).model_dump(mode="json")
    return json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ─────────────────────────── build / write / verify ────────────────────────────────


def build_receipt(
    task_id: str,
    started_at: datetime,
    finished_at: datetime,
    route_decisions: list[RouteDecision],
    tool_trace: list[ToolCall],
    artifacts: list[Path],
) -> TaskReceipt:
    """Assemble everything, hash artifacts, canonicalise, sign."""
    egress_events = read_egress(started_at, finished_at)
    external_egress_count = sum(1 for e in egress_events if e.is_external)

    chosen_model_ids = {d.chosen_model for d in route_decisions}
    model_manifests = {
        model_id: sha for model_id, sha in REGISTRY.manifest_hashes().items() if model_id in chosen_model_ids
    }

    artifact_hashes = {Path(p).name: file_sha256(Path(p)) for p in artifacts}

    payload_fields = {
        "task_id": task_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "model_manifests": model_manifests,
        "route_decisions": [d.model_dump(mode="json") for d in route_decisions],
        "tool_trace": [t.model_dump(mode="json") for t in tool_trace],
        "egress_events": [e.model_dump(mode="json") for e in egress_events],
        "external_egress_count": external_egress_count,
        "artifact_hashes": artifact_hashes,
    }
    payload = _canonical_payload(payload_fields)
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    signature_hex, public_key_hex = sign(payload)

    return TaskReceipt(
        task_id=task_id,
        started_at=started_at,
        finished_at=finished_at,
        model_manifests=model_manifests,
        route_decisions=route_decisions,
        tool_trace=tool_trace,
        egress_events=egress_events,
        external_egress_count=external_egress_count,
        artifact_hashes=artifact_hashes,
        payload_sha256=payload_sha256,
        signature_ed25519=signature_hex,
        public_key_ed25519=public_key_hex,
    )


def write_receipt(receipt: TaskReceipt) -> Path:
    """SETTINGS.paths.receipts / f'{task_id}.receipt.json'"""
    SETTINGS.paths.receipts.mkdir(parents=True, exist_ok=True)
    out_path = SETTINGS.paths.receipts / f"{receipt.task_id}.receipt.json"
    out_path.write_text(receipt.model_dump_json(indent=2))
    return out_path


def verify(receipt: TaskReceipt) -> tuple[bool, list[str]]:
    """Recompute payload hash, check signature, re-hash artifacts if present on disk,
    assert external_egress_count == 0. Returns (ok, problems)."""
    problems: list[str] = []
    fields = receipt.model_dump(mode="json")
    payload = _canonical_payload(fields)
    recomputed_hash = hashlib.sha256(payload).hexdigest()
    if recomputed_hash != receipt.payload_sha256:
        problems.append(
            f"payload hash mismatch: recomputed {recomputed_hash}, receipt claims {receipt.payload_sha256}"
        )

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(receipt.public_key_ed25519))
        public_key.verify(bytes.fromhex(receipt.signature_ed25519), payload)
    except Exception as exc:
        problems.append(f"signature verification failed: {exc}")

    for filename, expected_hash in receipt.artifact_hashes.items():
        candidates = [
            SETTINGS.paths.outputs / receipt.task_id / filename,
            SETTINGS.paths.outputs / filename,
        ]
        found = next((c for c in candidates if c.is_file()), None)
        if found is None:
            continue  # artifact not present on this machine — not itself a failure
        actual_hash = file_sha256(found)
        if actual_hash != expected_hash:
            problems.append(f"artifact {filename!r} hash mismatch: expected {expected_hash}, found {actual_hash}")

    if receipt.external_egress_count != 0:
        problems.append(f"external_egress_count is {receipt.external_egress_count}, must be 0 for a clean receipt")

    return (len(problems) == 0, problems)
