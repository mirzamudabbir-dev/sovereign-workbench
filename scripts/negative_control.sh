#!/usr/bin/env bash
# L8 — the negative-control demo. A monitor showing zero events proves nothing (it
# could be unplugged); a monitor that visibly catches something proves it is live.
# This is the demo move: run a real task (clean receipt), then deliberately try to
# reach the outside world and show Tetragon killing it while the real task's receipt
# stays clean.
#
# Requires a running tetragon container (docker-compose.yml, L0) with policies/
# mounted read-only at /etc/tetragon/tetragon.tp.d, and the container named "tetragon".
#
# Two things below were discovered wrong in an earlier draft of this script by actually
# running it against a real Tetragon container (Session 9, on colima) — recorded here so
# nobody "fixes" this script back into a version that only looks right on paper:
#
#   1. `docker cp <policy> tetragon:/etc/tetragon/tetragon.tp.d/` FAILS outright —
#      "Error response from daemon: mounted volume is marked read-only" — because
#      docker-compose.yml correctly mounts that path `:ro` (a compromised container must
#      not be able to rewrite its own security policy). This is not colima/macOS-specific;
#      it happens on any real Docker install with that compose file.
#   2. Even granting write access, Tetragon v1.1.2 does NOT hot-reload
#      tetragon.tp.d on a file appearing there — it only scans that directory at
#      container startup. The actual supported mechanism is its own client, `tetra`,
#      talking to the running daemon's gRPC API — see below.
set -euo pipefail

echo "1. Loading Tetragon ENFORCEMENT policy (via tetra, not docker cp — see header)…"
docker exec tetragon tetra tracingpolicy add /etc/tetragon/tetragon.tp.d/egress_enforce.yaml
sleep 2

echo "2. A normal task continues to work:"
python -m core.graph --demo doc_qa            # succeeds

echo "3. Now a process deliberately attempts an outbound connection:"
# On a real bare-metal Linux host (the venue box), Tetragon's pid:host/cgroup:host
# monitoring covers the WHOLE machine, so a plain `curl` here is exactly right and
# will be killed. On a macOS dev machine running Tetragon inside a colima/Lima Linux
# VM, only network activity that originates INSIDE that VM's own Docker is visible —
# confirmed empirically this session: a native macOS curl produces zero Tetragon
# events, while curlimages/curl run as a container is captured and killed for real.
# NEGATIVE_CONTROL_IN_CONTAINER=1 selects that dev-machine-safe substitute; leave unset
# on the real venue box.
if [ "${NEGATIVE_CONTROL_IN_CONTAINER:-0}" = "1" ]; then
  docker run --rm curlimages/curl:latest -m 5 -s -o /dev/null https://example.com \
    && echo "   (not killed — enforcement did not trigger)" \
    || echo "   → KILLED by Tetragon (exit code $?, expected 137 = SIGKILL)"
else
  curl -m 3 https://example.com || echo "   → KILLED by Tetragon"
fi

echo "4. Tetragon caught it:"
tail -5 data/tetragon/events.json | python -m json.tool

echo "5. The receipt for the real task is still clean:"
python scripts/verify_receipt.py "$(ls -t data/receipts/*.json | head -1)"

echo "6. Restoring OBSERVE-only policy (never leave enforcement loaded outside this demo)…"
docker exec tetragon tetra tracingpolicy delete egress-enforce
