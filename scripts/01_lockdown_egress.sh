#!/usr/bin/env bash
# L0 — default-deny outbound at the host firewall. This is the *claim* (R1); L8's
# Tetragon-based receipt is the *proof* (R16). Both are required, neither substitutes
# for the other. Run on the Ubuntu venue machine, AFTER scripts/00 and scripts/02
# (both need network) and BEFORE the demo.
set -euo pipefail

RED='\033[1;31m'
GREEN='\033[1;32m'
NC='\033[0m'

fail() {
  echo -e "${RED}LOCKDOWN FAILED: $1${NC}" >&2
  exit 1
}

if [[ "${1:-}" == "--undo" ]]; then
  echo "Flushing table inet sovereign (build-out mode — egress re-opened)"
  sudo nft flush table inet sovereign 2>/dev/null || true
  sudo nft delete table inet sovereign 2>/dev/null || true
  echo -e "${GREEN}Egress lockdown undone.${NC}"
  exit 0
fi

command -v nft >/dev/null 2>&1 || fail "nft not found — install nftables first (apt install nftables)"

sudo nft -f - <<'EOF' || fail "nft ruleset load failed"
table inet sovereign {
  chain output {
    type filter hook output priority 0; policy drop;
    oif "lo" accept
    ip daddr 127.0.0.0/8 accept
    ip daddr 172.16.0.0/12 accept          # docker bridge
    ct state established,related accept
    counter log prefix "SOVEREIGN-EGRESS-DROP " drop
  }
}
EOF

sudo nft list table inet sovereign || fail "could not list table inet sovereign after load"

# Disable systemd-resolved upstream DNS — loopback-only resolution.
if systemctl is-active --quiet systemd-resolved 2>/dev/null; then
  sudo mkdir -p /etc/systemd/resolved.conf.d
  printf '[Resolve]\nDNS=127.0.0.1\nFallbackDNS=\nDNSStubListener=yes\n' \
    | sudo tee /etc/systemd/resolved.conf.d/sovereign-no-upstream.conf >/dev/null
  sudo systemctl restart systemd-resolved || fail "could not restart systemd-resolved"
else
  echo "systemd-resolved not active — skipping DNS lockdown step"
fi

# Disable NTP sync — no outbound time sync in an air-gapped environment.
if command -v timedatectl >/dev/null 2>&1; then
  sudo timedatectl set-ntp false || fail "could not disable NTP sync"
else
  echo "timedatectl not found — skipping NTP lockdown step"
fi

# Docker's embedded DNS must not forward off-box.
DAEMON_JSON=/etc/docker/daemon.json
sudo mkdir -p "$(dirname "${DAEMON_JSON}")"
if [[ -s "${DAEMON_JSON}" ]]; then
  python3 - "${DAEMON_JSON}" <<'PYEOF' || fail "could not patch ${DAEMON_JSON}"
import json, sys
path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)
cfg["dns"] = ["127.0.0.1"]
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF
else
  echo '{"dns": ["127.0.0.1"]}' | sudo tee "${DAEMON_JSON}" >/dev/null
fi
sudo systemctl restart docker || fail "could not restart docker after daemon.json change"

echo -e "${GREEN}Egress lockdown applied. Default-deny outbound, DNS/NTP pinned to loopback.${NC}"
