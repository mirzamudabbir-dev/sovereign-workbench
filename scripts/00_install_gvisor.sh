#!/usr/bin/env bash
# L0 — installs gVisor (runsc) and registers it as a Docker runtime.
# Requires network. Run ONCE during build-out, on the Ubuntu venue machine,
# before scripts/01_lockdown_egress.sh closes the air gap.
#
# gVisor intercepts syscalls in userspace and blocks PCIe/GPU passthrough — this is
# expected and correct. The L5 sandbox never needs GPU access (it runs Python for
# calculations/spreadsheets/code tests, never inference). Do not add --gpus to the
# sandbox container to "fix" this.
set -euo pipefail

if command -v runsc >/dev/null 2>&1; then
  echo "runsc already installed at $(command -v runsc) — skipping download"
else
  ARCH=$(uname -m)
  URL="https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}"
  TMPDIR=$(mktemp -d)
  trap 'rm -rf "${TMPDIR}"' EXIT
  ( cd "${TMPDIR}" \
    && wget -q "${URL}/runsc" "${URL}/runsc.sha512" \
              "${URL}/containerd-shim-runsc-v1" "${URL}/containerd-shim-runsc-v1.sha512" \
    && sha512sum -c runsc.sha512 containerd-shim-runsc-v1.sha512 \
    && sudo install -m 755 -o root -g root runsc containerd-shim-runsc-v1 /usr/local/bin )
fi

sudo runsc install                # writes the runtime into /etc/docker/daemon.json
sudo systemctl restart docker

if docker run --rm --runtime=runsc alpine:3 uname -a | grep -qi linux; then
  echo "gVisor OK"
else
  echo -e "\033[1;31mgVisor smoke test FAILED — runsc runtime not usable.\033[0m" >&2
  echo "Fallback: set sandbox.runtime: runc in config.yaml and record why in PROGRESS.md." >&2
  echo "network_mode: none still holds — that is the property R1/R16 actually depend on." >&2
  exit 1
fi
