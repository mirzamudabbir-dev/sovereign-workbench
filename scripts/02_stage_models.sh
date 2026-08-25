#!/usr/bin/env bash
# L0 — downloads all weights while the network is still open, into models/, and
# records SHA256s. Run on the Ubuntu venue machine BEFORE scripts/01_lockdown_egress.sh.
# After this, every service env sets HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 — a
# stray model load attempting a network call at runtime is a hard R1 violation.
set -euo pipefail

command -v huggingface-cli >/dev/null 2>&1 || {
  echo -e "\033[1;31mhuggingface-cli not found. pip install -r requirements.txt first.\033[0m" >&2
  exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="${REPO_ROOT}/models"
mkdir -p "${MODELS_DIR}"

# repo id -> local dir slug (slug matches ModelManifest.id / config.yaml conventions)
declare -A MODELS=(
  ["Qwen/Qwen2.5-VL-7B-Instruct-AWQ"]="qwen25-vl-7b"
  ["Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"]="qwen25-coder-7b"
  ["katanemo/Arch-Router-1.5B"]="arch-router-1.5b"
  ["PaddlePaddle/PaddleOCR-VL"]="paddleocr-vl"
  ["BAAI/bge-m3"]="bge-m3"
)

for repo_id in "${!MODELS[@]}"; do
  slug="${MODELS[${repo_id}]}"
  dest="${MODELS_DIR}/${slug}"
  echo "== staging ${repo_id} -> ${dest} =="
  mkdir -p "${dest}"
  huggingface-cli download "${repo_id}" --local-dir "${dest}"
  ( cd "${dest}" && find . -type f ! -name SHA256SUMS -exec sha256sum {} \; > SHA256SUMS )
  echo "== ${slug} staged, $(wc -l < "${dest}/SHA256SUMS") files hashed =="
done

echo "All models staged under ${MODELS_DIR}. You may now run scripts/01_lockdown_egress.sh."
