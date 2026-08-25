#!/usr/bin/env bash
# L0 — stops everything started by scripts/03_start_services.sh: the four vLLM
# processes, the FastAPI backend, the Streamlit UI, then the docker compose stack.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${REPO_ROOT}/run"

for pidfile in "${RUN_DIR}"/*.pid; do
  [[ -e "${pidfile}" ]] || continue
  name="$(basename "${pidfile}" .pid)"
  pid="$(cat "${pidfile}")"
  if kill -0 "${pid}" 2>/dev/null; then
    echo "stopping ${name} (pid ${pid})"
    kill "${pid}"
    for _ in $(seq 1 10); do
      kill -0 "${pid}" 2>/dev/null || break
      sleep 1
    done
    kill -0 "${pid}" 2>/dev/null && kill -9 "${pid}" 2>/dev/null
  else
    echo "${name} not running (stale pidfile)"
  fi
  rm -f "${pidfile}"
done

echo "== docker compose down (qdrant, tetragon) =="
( cd "${REPO_ROOT}" && docker compose down )

echo "All services stopped."
