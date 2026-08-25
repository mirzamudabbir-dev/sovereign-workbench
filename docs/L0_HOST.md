# L0 — HOST SUBSTRATE

## MISSION LOCK

**Build:** the machine state that makes the air gap true — default-deny egress, gVisor runtime,
Qdrant + Tetragon containers, model weight staging, and the `make` targets that start everything.

**You are NOT building:** any Python in `core/`, any model logic, any UI. If you find yourself
writing `import openai`, you are in the wrong layer — stop.

**Serves:** R1 (air-gapped, nothing leaves premises), R11 (single workstation).

**Files You Own** (create/edit only these):
```
config.yaml
requirements.txt
Makefile
scripts/00_install_gvisor.sh
scripts/01_lockdown_egress.sh
scripts/02_stage_models.sh
scripts/03_start_services.sh
scripts/04_stop_services.sh
scripts/preflight.py
docker-compose.yml
.gitignore
```

**Files You May NOT Touch:** anything in `core/`, `docs/`, `manifests/`, `api.py`, `ui.py`.

---

## Target hardware

Single workstation, one NVIDIA GPU with **≥24 GB VRAM** (RTX 4090 / 5090 / A6000), 64 GB system
RAM, 500 GB SSD, Ubuntu 22.04, NVIDIA driver ≥ 550, CUDA 12.x, Docker with `nvidia-container-toolkit`.

**VRAM budget — this is the constraint that makes R2+R11 simultaneously true.**
All four models stay resident. No swapping, no Sleep Mode (that is an optimization, out of scope).

| Service | Model | `--gpu-memory-utilization` | ≈VRAM on 24 GB |
|---|---|---|---|
| :8001 | `Qwen/Qwen2.5-VL-7B-Instruct-AWQ` | `0.28` | 6.7 GB |
| :8002 | `Qwen/Qwen2.5-Coder-7B-Instruct-AWQ` | `0.20` | 4.8 GB |
| :8003 | `katanemo/Arch-Router-1.5B` | `0.11` | 2.6 GB |
| :8004 | `PaddlePaddle/PaddleOCR-VL` | `0.13` | 3.1 GB |
| in-proc | `BAAI/bge-m3` (sentence-transformers) | — | ~1.3 GB |
| | **Total** | **0.72** | **~18.5 GB**, ~5.5 GB free |

If the venue GPU is smaller than 24 GB, the documented fallback is: disable :8002 in
`manifests/`, and let :8001 serve coding too. **Do not change the architecture** — that is
exactly the R4 property being demonstrated.

---

## Build order within this session

### 1. `scripts/00_install_gvisor.sh`

Install gVisor and register `runsc` as a Docker runtime. gVisor is the sandbox runtime for L5.

```bash
#!/usr/bin/env bash
set -euo pipefail
# Requires network. Run ONCE during build-out, before the air gap is closed.
ARCH=$(uname -m)
URL="https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}"
wget -q "${URL}/runsc" "${URL}/runsc.sha512" \
     "${URL}/containerd-shim-runsc-v1" "${URL}/containerd-shim-runsc-v1.sha512"
sha512sum -c runsc.sha512 containerd-shim-runsc-v1.sha512
sudo install -m 755 -o root -g root runsc containerd-shim-runsc-v1 /usr/local/bin
rm -f runsc* containerd-shim-runsc-v1*
sudo runsc install                # writes the runtime into /etc/docker/daemon.json
sudo systemctl restart docker
docker run --rm --runtime=runsc alpine:3 uname -a | grep -qi linux && echo "gVisor OK"
```

**Known constraint you must respect (do not fight it):** gVisor intercepts syscalls in
userspace and **blocks PCIe/GPU passthrough**. The L5 sandbox therefore has **no GPU**. This is
correct — the sandbox runs Python for calculations, spreadsheets and code tests, never inference.
Do not add `--gpus` to the sandbox container. Do not switch to Firecracker to "fix" this.

If `runsc install` fails on the venue machine, the fallback is `runtime: runc` in `config.yaml`.
`network_mode: none` still holds, which is the property R1/R16 actually depend on. Record the
fallback in `PROGRESS.md`; do not silently change the default.

### 2. `scripts/01_lockdown_egress.sh`

Default-deny outbound at the host firewall. This is the *claim*; L8 is the *proof*. Both required.

```bash
#!/usr/bin/env bash
set -euo pipefail
sudo nft -f - <<'EOF'
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
sudo nft list table inet sovereign
```

Also: disable systemd-resolved upstream DNS, disable NTP sync, and add a `--dns 127.0.0.1`
default to `/etc/docker/daemon.json`. Print a red banner if any of these fail.

Add a `--undo` flag that flushes the table, for the build-out phase.

### 3. `scripts/02_stage_models.sh`

Downloads all weights **while the network is still open**, into `models/`, then records SHA256s.

```bash
MODELS=(
  "Qwen/Qwen2.5-VL-7B-Instruct-AWQ"
  "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
  "katanemo/Arch-Router-1.5B"
  "PaddlePaddle/PaddleOCR-VL"
  "BAAI/bge-m3"
)
# huggingface-cli download <id> --local-dir models/<slug>
# then: find models/<slug> -type f -exec sha256sum {} \; > models/<slug>/SHA256SUMS
```

After this runs, set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` in every service env.
**This is mandatory** — without it a stray model load attempts a network call and breaks R1.

### 4. `docker-compose.yml`

Only two containers. vLLM runs on the host (bare metal) so it sees the GPU without extra plumbing.

```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.12.0
    ports: ["127.0.0.1:6333:6333"]
    volumes: ["./data/qdrant:/qdrant/storage"]
    restart: unless-stopped

  tetragon:
    image: quay.io/cilium/tetragon:v1.1.2
    pid: host
    cgroup: host
    privileged: true
    volumes:
      - /sys/kernel/btf/vmlinux:/var/lib/tetragon/btf:ro
      - /proc:/procRoot:ro
      - ./policies:/etc/tetragon/tetragon.tp.d:ro
      - ./data/tetragon:/var/log/tetragon
    command: ["--export-filename", "/var/log/tetragon/events.json"]
    restart: unless-stopped
```

`policies/` is populated by L8, not you. Create the empty dir with a `.gitkeep`.

### 5. `scripts/03_start_services.sh`

Starts the four vLLM servers as background processes with PID files in `run/`.
Every invocation includes: `--host 127.0.0.1`, `HF_HUB_OFFLINE=1`, the `--gpu-memory-utilization`
from the table above, `--served-model-name` matching the manifest, and `--max-model-len` per model
(32768 / 16384 / 8192 / 16384). Wait-for-healthy loop on `/health` before returning.

Then `docker compose up -d`, then `uvicorn api:app --host 127.0.0.1 --port 8000`,
then `streamlit run ui.py --server.address 127.0.0.1 --server.port 8501`.

### 6. `scripts/preflight.py`

The single most useful thing you will write. Run before every demo. Checks, in order:

1. GPU present, free VRAM ≥ 20 GB
2. All four vLLM `/v1/models` endpoints answer, and the returned model name matches the manifest
3. Qdrant `/healthz` OK, Tetragon container running, `events.json` growing
4. `docker run --rm --runtime=runsc --network=none alpine:3 true` succeeds
5. **Negative control:** `docker run --rm --network=none alpine:3 wget -T2 -q -O- http://1.1.1.1`
   must FAIL. If it succeeds, print a red banner and exit 1.
6. `HF_HUB_OFFLINE=1` present in every service env
7. All templates in `templates/` exist and open

Output a green/red table. Exit non-zero on any red.

### 7. `config.yaml` and `requirements.txt`

`config.yaml` must match `Settings` in `docs/01_CONTRACTS.md` field-for-field.

```txt
# requirements.txt — pinned, no extras
vllm==0.6.6
langgraph==0.2.60
langgraph-checkpoint-sqlite==2.0.1
fastapi==0.115.6
uvicorn[standard]==0.34.0
streamlit==1.41.1
docling==2.15.0
qdrant-client==1.12.1
sentence-transformers==3.3.1
docxtpl==0.19.0
python-docx==1.1.2
python-pptx==1.0.2
openpyxl==3.1.5
docker==7.1.0
pydantic==2.10.4
pyyaml==6.0.2
cryptography==44.0.0
pillow==11.0.0
pymupdf==1.25.1
openai==1.59.6
pytest==8.3.4
httpx==0.28.1
```

Do not add to this list without recording the justification in `PROGRESS.md`.

### 8. `Makefile`

```
setup      # 00 + 02 (network required)
lockdown   # 01
start      # 03
stop       # 04
preflight  # scripts/preflight.py
demo       # preflight && start && open UI
test       # pytest tests/ -v
```

---

## Definition of Done

```bash
make preflight
```
exits 0 with every check green, **including check 5 (the negative control failing correctly)**,
and `nft list table inet sovereign` shows `policy drop`.

## Drift tripwires for this layer

- ❌ Adding Kubernetes, Helm, or Cilium CNI. You need Tetragon standalone, not a cluster.
- ❌ Adding Prometheus/Grafana. `preflight.py` is your observability.
- ❌ Giving the sandbox container GPU access.
- ❌ Binding any service to `0.0.0.0`.
- ❌ Writing Python that imports from `core/`.
- ❌ "Improving" the VRAM budget with Sleep Mode / model swapping. Explicitly out of scope.

## Session exit

Append to `PROGRESS.md`:
- Whether `runsc` installed successfully, or the `runc` fallback is in effect
- Actual free VRAM measured on this machine
- Any `requirements.txt` version that had to change, and why
- `## Next action: Session 0 (CONTRACTS) — implement core/schemas.py and core/config.py`
