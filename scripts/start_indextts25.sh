#!/usr/bin/env bash
set -euo pipefail

MODEL="${AI_DRAMA_P14_INDEXTTS_MODEL:-IndexTeam/IndexTTS-2.5}"
PORT="${INDEXTTS_PORT:-8092}"

if ! command -v vllm >/dev/null 2>&1; then
  echo "ERROR: vllm command not found. Install the IndexTTS-2.5/vLLM-Omni runtime first." >&2
  exit 1
fi

if [[ "$MODEL" != "IndexTeam/IndexTTS-2.5" ]]; then
  echo "ERROR: P14 is locked to IndexTeam/IndexTTS-2.5, got: $MODEL" >&2
  exit 1
fi

echo "Starting IndexTTS-2.5 on port $PORT ..."
exec vllm serve "$MODEL" --omni --trust-remote-code --port "$PORT"
