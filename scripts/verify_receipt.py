#!/usr/bin/env python3
"""L8 — the standalone auditor.

    python scripts/verify_receipt.py data/receipts/t-20260825-a1b2c3.receipt.json

Deliberately imports NOTHING from this project (only json, hashlib, pathlib, sys,
datetime and cryptography) — an auditor must be able to check a receipt without
trusting, or even having, this application's code. Everything this script needs to
know about a TaskReceipt's shape is inlined below as plain dict field access, not a
core.schemas import.

Canonicalisation note: this script re-serializes the exact field VALUES already parsed
from the receipt JSON file (strings, ints, nested dicts) rather than reconstructing
datetimes or model objects from scratch — core.receipt.py's canonical payload is built
the same way (json.dumps(..., sort_keys=True, separators=(',',':'))), so round-tripping
the already-serialized values through json.load -> json.dumps reproduces byte-identical
output. It must, since the whole point of a payload hash is that anyone can recompute it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# The 9 TaskReceipt fields that make up the signed payload — must match
# core/receipt.py's _ReceiptPayload field set exactly, in ANY order (json.dumps'
# sort_keys=True makes key order irrelevant to the resulting bytes).
_PAYLOAD_FIELDS = (
    "task_id", "started_at", "finished_at", "model_manifests",
    "route_decisions", "tool_trace", "egress_events",
    "external_egress_count", "artifact_hashes",
)


def _canonical_payload(receipt: dict) -> bytes:
    ordered = {k: receipt[k] for k in _PAYLOAD_FIELDS}
    return json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <receipt.json>", file=sys.stderr)
        return 2

    receipt_path = Path(argv[1])
    if not receipt_path.is_file():
        print(f"no such file: {receipt_path}", file=sys.stderr)
        return 2

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    problems: list[str] = []

    task_id = receipt.get("task_id", "?")
    print(f"Receipt        {task_id}")

    payload = _canonical_payload(receipt)
    recomputed_hash = hashlib.sha256(payload).hexdigest()
    claimed_hash = receipt.get("payload_sha256", "")
    if recomputed_hash == claimed_hash:
        print("Payload hash   MATCHES")
    else:
        print(f"Payload hash   MISMATCH (recomputed {recomputed_hash}, receipt claims {claimed_hash})")
        problems.append("payload hash mismatch")

    public_key_hex = receipt.get("public_key_ed25519", "")
    signature_hex = receipt.get("signature_ed25519", "")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(bytes.fromhex(signature_hex), payload)
        key_short = public_key_hex[:8] if public_key_hex else "?"
        print(f"Signature      VALID (ed25519, key {key_short}…)")
    except Exception as exc:
        print(f"Signature      INVALID ({exc})")
        problems.append("signature invalid")

    model_manifests = receipt.get("model_manifests", {})
    models_str = ", ".join(f"{model_id} (sha {sha[:8]}…)" for model_id, sha in sorted(model_manifests.items()))
    print(f"Models used    {models_str or '(none)'}")

    tool_trace = receipt.get("tool_trace", [])
    print(f"Tool calls     {len(tool_trace)}  (all recorded)")

    egress_events = receipt.get("egress_events", [])
    external_count = receipt.get("external_egress_count", -1)
    internal_count = len(egress_events) - max(external_count, 0)
    print(f"Egress events  {len(egress_events)} observed — {internal_count} internal, {external_count} external")
    if external_count != 0:
        problems.append(f"external_egress_count is {external_count}, must be 0")

    artifact_hashes = receipt.get("artifact_hashes", {})
    repo_root = receipt_path.resolve().parent.parent.parent  # data/receipts/X.json -> data/ -> repo root
    outputs_dir = repo_root / "data" / "outputs" / task_id
    if artifact_hashes:
        for filename, expected_hash in sorted(artifact_hashes.items()):
            candidates = [outputs_dir / filename, repo_root / "data" / "outputs" / filename]
            found = next((c for c in candidates if c.is_file()), None)
            if found is None:
                print(f"Artifacts      {filename}  NOT FOUND on this machine (hash not checked)")
                continue
            actual_hash = _sha256_file(found)
            if actual_hash == expected_hash:
                print(f"Artifacts      {filename}  sha256 MATCHES")
            else:
                print(f"Artifacts      {filename}  sha256 MISMATCH")
                problems.append(f"artifact {filename!r} hash mismatch")
    else:
        print("Artifacts      (none)")

    if problems:
        print(f"VERDICT        ❌ NOT SOVEREIGN — {'; '.join(problems)}")
        return 1

    print("VERDICT        ✅ SOVEREIGN — no external connection during this task")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
