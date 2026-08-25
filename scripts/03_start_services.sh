#!/usr/bin/env bash
# L0 — starts the four vLLM servers as background processes (bare metal, so they see
# the GPU without extra plumbing), then Qdrant + Tetragon via docker compose, then the
# FastAPI backend and Streamlit UI. All services bind 127.0.0.1 only — never 0.0.0.0.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${REPO_ROOT}/run"
LOG_DIR="${RUN_DIR}/logs"
mkdir -p "${RUN_DIR}" "${LOG_DIR}" "${REPO_ROOT}/policies" \
         "${REPO_ROOT}/data/qdrant" "${REPO_ROOT}/data/tetragon"

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

wait_healthy() {
  local port="$1" name="$2" tries=60
  echo -n "waiting for ${name} on :${port} "
  until curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1; do
    tries=$((tries - 1))
    if [[ "${tries}" -le 0 ]]; then
      echo "TIMEOUT"
      return 1
    fi
    echo -n "."
    sleep 5
  done
  echo " healthy"
}

start_vllm() {
  local name="$1" port="$2" served_name="$3" model_path="$4" \
        max_len="$5" gpu_util="$6" quantization="$7"
  local pidfile="${RUN_DIR}/${name}.pid"

  if [[ -f "${pidfile}" ]] && kill -0 "$(cat "${pidfile}")" 2>/dev/null; then
    echo "${name} already running (pid $(cat "${pidfile}")) — skipping"
    return 0
  fi

  local extra=()
  [[ "${quantization}" != "none" ]] && extra+=(--quantization "${quantization}")

  nohup vllm serve "${model_path}" \
    --host 127.0.0.1 --port "${port}" \
    --served-model-name "${served_name}" \
    --gpu-memory-utilization "${gpu_util}" \
    --max-model-len "${max_len}" \
    "${extra[@]}" \
    > "${LOG_DIR}/${name}.log" 2>&1 &
  echo $! > "${pidfile}"
  wait_healthy "${port}" "${name}"
}

MODELS_DIR="${REPO_ROOT}/models"
start_vllm "qwen25-vl-7b"      8001 "qwen25-vl-7b"      "${MODELS_DIR}/qwen25-vl-7b"      32768 0.28 awq
start_vllm "qwen25-coder-7b"   8002 "qwen25-coder-7b"   "${MODELS_DIR}/qwen25-coder-7b"   16384 0.20 awq
start_vllm "arch-router-1.5b"  8003 "arch-router-1.5b"  "${MODELS_DIR}/arch-router-1.5b"   8192 0.11 none
start_vllm "paddleocr-vl"      8004 "paddleocr-vl"      "${MODELS_DIR}/paddleocr-vl"      16384 0.13 none

echo "== docker compose up (qdrant, tetragon) =="
( cd "${REPO_ROOT}" && docker compose up -d )

echo "== FastAPI backend =="
if [[ -f "${REPO_ROOT}/api.py" ]]; then
  nohup uvicorn api:app --host 127.0.0.1 --port 8000 \
    > "${LOG_DIR}/api.log" 2>&1 &
  echo $! > "${RUN_DIR}/api.pid"
else
  echo "api.py not built yet (L7) — skipping"
fi

echo "== Streamlit UI =="
if [[ -f "${REPO_ROOT}/ui.py" ]]; then
  nohup streamlit run ui.py --server.address 127.0.0.1 --server.port 8501 \
    > "${LOG_DIR}/ui.log" 2>&1 &
  echo $! > "${RUN_DIR}/ui.pid"
else
  echo "ui.py not built yet (L7) — skipping"
fi

echo "All available services started. PID files in ${RUN_DIR}, logs in ${LOG_DIR}."
