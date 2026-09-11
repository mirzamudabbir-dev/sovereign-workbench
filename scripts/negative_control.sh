#!/usr/bin/env bash
# L8 — the negative-control demo. A monitor showing zero events proves nothing (it
# could be unplugged); a monitor that visibly catches something proves it is live.
# This is the demo move: run a real task (clean receipt), then deliberately try to
# reach the outside world and show Tetragon killing it while the real task's receipt
# stays clean.
#
# Requires the Linux/venue setup: a running tetragon container (docker-compose.yml,
# L0) with policies/ mounted at /etc/tetragon/tetragon.tp.d. Swaps in
# policies/egress_enforce.yaml for the duration of this script only — restore
# egress_observe.yaml immediately after for any real task.
set -euo pipefail

echo "1. Loading Tetragon ENFORCEMENT policy…"
docker cp policies/egress_enforce.yaml tetragon:/etc/tetragon/tetragon.tp.d/
sleep 3

echo "2. A normal task continues to work:"
python -m core.graph --demo doc_qa            # succeeds

echo "3. Now a process deliberately attempts an outbound connection:"
curl -m 3 https://example.com || echo "   → KILLED by Tetragon"

echo "4. Tetragon caught it:"
tail -5 data/tetragon/events.json | python -m json.tool

echo "5. The receipt for the real task is still clean:"
python scripts/verify_receipt.py "$(ls -t data/receipts/*.json | head -1)"

echo "6. Restoring OBSERVE-only policy (never leave enforcement loaded outside this demo)…"
docker cp policies/egress_observe.yaml tetragon:/etc/tetragon/tetragon.tp.d/
