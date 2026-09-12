#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MODEL_ID="IndexTeam/IndexTTS-2.5"
MODEL_DIR="${INDEXTTS_MODEL_DIR:-$REPO_ROOT/.models/IndexTTS-2.5}"

if ! command -v modelscope >/dev/null 2>&1; then
  echo "ERROR: modelscope command not found." >&2
  echo "Install it first, for example: pip install -U modelscope" >&2
  exit 1
fi

mkdir -p "$(dirname "$MODEL_DIR")"
echo "Downloading $MODEL_ID from ModelScope to: $MODEL_DIR"
modelscope download --model "$MODEL_ID" --local_dir "$MODEL_DIR"

echo "IndexTTS-2.5 model bundle is ready at: $MODEL_DIR"
