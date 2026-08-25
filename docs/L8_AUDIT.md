# L8 — EVIDENCE & AUDIT PLANE

## MISSION LOCK

**Build:** kernel-level egress observation with Tetragon, and a signed, offline-verifiable
`TaskReceipt` per task proving no external call occurred.

**You are NOT building:** anything in the task path. This layer *observes*; it must never be
able to alter a task's behaviour. No LLM calls, no tools, no UI logic.

**Serves:** R1 and R16 — the requirement the PS itself calls *"the actual proof of the sovereign
claim, not just a statement of it."*

**Files You Own:**
```
core/receipt.py
policies/egress_observe.yaml
policies/egress_enforce.yaml
scripts/verify_receipt.py
scripts/negative_control.sh
tests/test_receipt.py
```

---

## Why this layer wins the demo

Every team will say "it's air-gapped." Almost none will be able to *prove* it. Three things
make your proof different:

1. **Kernel level.** Tetragon's kprobe on `tcp_connect` sees the real destination regardless of
   proxy settings, `/etc/hosts`, or application-level lying.
2. **Signed and offline-verifiable.** A receipt can be checked weeks later, on another machine,
   by someone who does not trust your UI or your code.
3. **A live negative control.** A monitor showing zero events proves nothing — it could be
   unplugged. A monitor that *visibly catches something* proves it is live.

Point 3 is the demo move. Build it deliberately.

---

## Tetragon policies

`policies/egress_observe.yaml` — always loaded. Observes every outbound connect on the host:

```yaml
apiVersion: cilium.io/v1alpha1
kind: TracingPolicy
metadata:
  name: "egress-observe"
spec:
  kprobes:
    - call: "tcp_connect"
      syscall: false
      args:
        - index: 0
          type: "sock"
      selectors:
        - matchArgs:
            - index: 0
              operator: "NotDAddr"
              values:
                - 127.0.0.1
                - 172.16.0.0/12
                - 10.0.0.0/8
                - 192.168.0.0/16
```

`policies/egress_enforce.yaml` — same matcher plus `matchActions: [{action: Sigkill}]`.
**Load this only for the negative-control demo**, so an outbound attempt is visibly killed.
Document the two-file split in `PROGRESS.md`; do not merge them.

Events land in `data/tetragon/events.json` (JSONL, one event per line).

---

## `core/receipt.py` — required API

```python
"""L8 — sovereignty receipts. Observes; never participates."""

TETRAGON_LOG = SETTINGS.paths.data / "tetragon" / "events.json"

def is_external(ip: str) -> bool:
    """False for loopback, RFC1918, link-local, multicast. True otherwise.
    Use ipaddress stdlib. This one function decides whether a receipt is clean —
    unit-test it against a table of ~20 addresses."""


def read_egress(started_at: datetime, finished_at: datetime) -> list[EgressEvent]:
    """Tail TETRAGON_LOG, parse JSONL, keep process_kprobe events for tcp_connect whose
    timestamp falls in [started_at, finished_at]. Map to EgressEvent.
    If the log is missing or empty -> raise WorkbenchError. A receipt with no monitor data
    is WORSE than no receipt: it is an unverifiable claim. Never silently emit zero events."""


def build_receipt(task_id, started_at, finished_at, route_decisions, tool_trace,
                  artifacts: list[Path]) -> TaskReceipt:
    """Assemble everything, hash artifacts, canonicalise, sign."""


def _canonical_payload(receipt_fields: dict) -> bytes:
    """json.dumps(..., sort_keys=True, separators=(',',':'), default=str).encode()
    Deterministic — verify_receipt must reproduce this byte-for-byte."""


def sign(payload: bytes) -> tuple[str, str]:
    """Ed25519 via cryptography. Private key at SETTINGS.paths.data/'signing_key.pem',
    generated on first use with mode 0600. Returns (signature_hex, public_key_hex)."""


def verify(receipt: TaskReceipt) -> tuple[bool, list[str]]:
    """Recompute payload hash, check signature, re-hash artifacts if present on disk,
    assert external_egress_count == 0. Returns (ok, problems)."""


def write_receipt(receipt: TaskReceipt) -> Path:
    """SETTINGS.paths.receipts / f'{task_id}.receipt.json'"""
```

L4's `node_emit` calls `build_receipt()` then `write_receipt()`. That is the only coupling.

---

## `scripts/verify_receipt.py` — the standalone auditor

```bash
python scripts/verify_receipt.py data/receipts/t-20260825-a1b2c3.receipt.json
```

Must import **only** `json`, `hashlib`, `pathlib`, `sys`, `datetime` and `cryptography`.
No `core.*` imports at all. This is the point: an auditor runs it without your application.

Output:
```
Receipt        t-20260825-a1b2c3
Signature      VALID (ed25519, key 4f2a…)
Payload hash   MATCHES
Models used    qwen25-vl-7b (sha 9c1e…), qwen25-coder-7b (sha 71bd…)
Tool calls     14  (all recorded)
Egress events  3 observed — 3 internal, 0 external
Artifacts      approval_note.docx  sha256 MATCHES
VERDICT        ✅ SOVEREIGN — no external connection during this task
```
Exit 0 only on a fully clean verdict.

---

## `scripts/negative_control.sh` — the demo centrepiece

```bash
#!/usr/bin/env bash
set -euo pipefail
echo "1. Loading Tetragon ENFORCEMENT policy…"
docker cp policies/egress_enforce.yaml tetragon:/etc/tetragon/tetragon.tp.d/ && sleep 3

echo "2. A normal task continues to work:"
python -m core.graph --demo doc_qa            # succeeds

echo "3. Now a process deliberately attempts an outbound connection:"
curl -m 3 https://example.com || echo "   → KILLED by Tetragon"

echo "4. Tetragon caught it:"
tail -5 data/tetragon/events.json | python -m json.tool

echo "5. The receipt for the real task is still clean:"
python scripts/verify_receipt.py "$(ls -t data/receipts/*.json | head -1)"
```

Rehearse this. Then hand the judges the network cable.

---

## Tests — `tests/test_receipt.py`

```python
def test_is_external_table()                  # ~20 addresses, both classes
def test_canonical_payload_is_deterministic() # same dict twice -> identical bytes
def test_sign_then_verify_roundtrip()
def test_tampered_field_fails_verification()  # flip one char in a route reason
def test_tampered_artifact_hash_fails()
def test_missing_tetragon_log_raises()        # NEVER silently returns []
def test_external_event_sets_count_and_fails_verify()
def test_receipt_json_is_stable_across_runs()

@pytest.mark.integration
def test_live_capture_sees_internal_connections()   # a real qdrant call appears as internal
def test_negative_control_produces_external_event()
```

`test_missing_tetragon_log_raises` is the integrity test. A receipt that reports zero egress
because the monitor was dead is the exact failure mode this layer exists to prevent.

---

## Definition of Done

```bash
pytest tests/test_receipt.py -v -m "not integration"
python -m core.graph --demo doc_qa
python scripts/verify_receipt.py "$(ls -t data/receipts/*.json | head -1)"   # → exit 0, ✅
bash scripts/negative_control.sh                                             # → visibly killed
```

## Drift tripwires

- ❌ Generating the receipt from application logs instead of the kernel monitor. Circular.
- ❌ Letting `read_egress` return `[]` when the log is missing. Raise.
- ❌ Making `verify_receipt.py` import `core.*`. It must stand alone.
- ❌ Adding Falco, Prometheus, Grafana, or a SIEM.
- ❌ Letting L8 modify task state, retry anything, or block a task.
- ❌ Non-deterministic JSON serialisation (unsorted keys, float repr drift).
- ❌ Committing `signing_key.pem`. Add it to `.gitignore`.

## Session exit

`PROGRESS.md`: observed event volume per task, whether enforcement policy killed `curl`,
verify_receipt output pasted in full.
`## Next action: L7 — api.py + ui.py (Streamlit workbench)`
