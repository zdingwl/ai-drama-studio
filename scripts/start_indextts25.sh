#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVED_MODEL="IndexTeam/IndexTTS-2.5"
MODEL_DIR="${INDEXTTS_MODEL_DIR:-$REPO_ROOT/.models/IndexTTS-2.5}"
PORT="${INDEXTTS_PORT:-8092}"

if ! command -v vllm >/dev/null 2>&1; then
  echo "ERROR: vllm command not found. Install vLLM-Omni with IndexTTS support first." >&2
  echo "Official package requirement: vllm-omni[indextts2]" >&2
  exit 1
fi

if [[ ! -d "$MODEL_DIR" ]] || [[ -z "$(find "$MODEL_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  echo "ERROR: local IndexTTS-2.5 model bundle not found at: $MODEL_DIR" >&2
  echo "Run ./scripts/download_indextts25_model.sh first, or set INDEXTTS_MODEL_DIR." >&2
  exit 1
fi

echo "Starting $SERVED_MODEL from local bundle: $MODEL_DIR"
echo "Listening on port $PORT; canonical served model name remains $SERVED_MODEL"
exec vllm serve "$MODEL_DIR" \
  --served-model-name "$SERVED_MODEL" \
  --omni \
  --trust-remote-code \
  --port "$PORT"
