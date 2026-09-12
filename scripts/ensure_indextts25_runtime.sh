#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MODEL_ID="IndexTeam/IndexTTS-2.5"
MODEL_DIR="${INDEXTTS_MODEL_DIR:-$REPO_ROOT/.models/IndexTTS-2.5}"
RUNTIME_ROOT="${INDEXTTS_RUNTIME_DIR:-$REPO_ROOT/.runtime/indextts25}"
VENV="$RUNTIME_ROOT/venv"
STACK_ID="vllm-0.28.0__vllm-omni-0.28.0__indextts2"
STAMP="$RUNTIME_ROOT/stack.txt"
PORT="${INDEXTTS_PORT:-8092}"

mkdir -p "$RUNTIME_ROOT" "$REPO_ROOT/.models"

resolve_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return
  fi

  if command -v python3 >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then
    local bootstrap="$RUNTIME_ROOT/uv-bootstrap"
    if [[ ! -x "$bootstrap/bin/uv" ]]; then
      python3 -m venv "$bootstrap"
      "$bootstrap/bin/python" -m pip install --upgrade pip uv
    fi
    echo "$bootstrap/bin/uv"
    return
  fi

  if command -v curl >/dev/null 2>&1; then
    echo "[IndexTTS] uv not found; installing the official uv user binary..." >&2
    curl -LsSf https://astral.sh/uv/install.sh | sh >&2
    if [[ -x "$HOME/.local/bin/uv" ]]; then
      echo "$HOME/.local/bin/uv"
      return
    fi
    if [[ -x "$HOME/.cargo/bin/uv" ]]; then
      echo "$HOME/.cargo/bin/uv"
      return
    fi
  fi

  echo "ERROR: cannot bootstrap uv. WSL/Linux needs either uv, python3+pip, or curl." >&2
  exit 1
}

UV="$(resolve_uv)"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "[IndexTTS] creating isolated Python 3.12 runtime at $VENV"
  "$UV" python install 3.12
  "$UV" venv --python 3.12 --seed "$VENV"
fi

PY="$VENV/bin/python"
UV_ARGS=(--python "$PY")
if [[ -n "${AI_DRAMA_PYPI_INDEX:-}" ]]; then
  UV_ARGS+=(--default-index "$AI_DRAMA_PYPI_INDEX")
fi

CURRENT_STAMP=""
[[ -f "$STAMP" ]] && CURRENT_STAMP="$(cat "$STAMP")"
if [[ "$CURRENT_STAMP" != "$STACK_ID" ]] || ! "$PY" -c "import vllm, vllm_omni, modelscope" >/dev/null 2>&1; then
  echo "[IndexTTS] installing isolated vLLM/vLLM-Omni runtime (first start only)..."
  "$UV" pip install "${UV_ARGS[@]}" --torch-backend=auto 'vllm==0.28.0'
  "$UV" pip install "${UV_ARGS[@]}" 'vllm-omni[indextts2]==0.28.0' 'modelscope>=1.28'
  printf '%s' "$STACK_ID" > "$STAMP"
fi

if [[ ! -f "$MODEL_DIR/config.yaml" ]]; then
  echo "[IndexTTS] model bundle is missing; downloading $MODEL_ID from ModelScope..."
  mkdir -p "$MODEL_DIR"
  "$VENV/bin/modelscope" download --model "$MODEL_ID" --local_dir "$MODEL_DIR"
fi

if [[ ! -f "$MODEL_DIR/config.yaml" ]]; then
  echo "ERROR: ModelScope download completed without $MODEL_DIR/config.yaml" >&2
  exit 1
fi

DEPLOY_CONFIG="$($PY - <<'PY'
from pathlib import Path
import vllm_omni
path = Path(vllm_omni.__file__).resolve().parent / "deploy" / "indextts2_5.yaml"
print(path)
PY
)"
if [[ ! -f "$DEPLOY_CONFIG" ]]; then
  echo "ERROR: vLLM-Omni runtime does not contain indextts2_5.yaml: $DEPLOY_CONFIG" >&2
  exit 1
fi

# IndexTTS may lazily fetch auxiliary assets. In mainland-China development,
# default those Hugging Face lookups to a mirror while allowing explicit override.
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export FLASHINFER_DISABLE_VERSION_CHECK="${FLASHINFER_DISABLE_VERSION_CHECK:-1}"

echo "[IndexTTS] starting managed IndexTTS-2.5"
echo "[IndexTTS] model: $MODEL_DIR"
echo "[IndexTTS] deploy config: $DEPLOY_CONFIG"
echo "[IndexTTS] endpoint: http://127.0.0.1:$PORT/v1"

exec "$VENV/bin/vllm" serve "$MODEL_DIR" \
  --served-model-name "$MODEL_ID" \
  --omni \
  --trust-remote-code \
  --deploy-config "$DEPLOY_CONFIG" \
  --host 127.0.0.1 \
  --port "$PORT"
