#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHISPER_DIR="${ROOT_DIR}/third_party/whisper.cpp"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
WHISPER_MODEL_NAME="${WHISPER_MODEL_NAME:-base.en}"
WHISPER_MODEL_PATH="${WHISPER_DIR}/models/ggml-${WHISPER_MODEL_NAME}.bin"
WHISPER_BIN_PATH="${WHISPER_DIR}/build/bin/whisper-cli"

log() {
  printf '\n[%s] %s\n' "setup-local-mac" "$1"
}

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required command: ${name}" >&2
    exit 1
  fi
}

log "Checking local prerequisites"
require_cmd ollama
require_cmd say
require_cmd git
require_cmd cmake

if ! ollama list >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Ollama is installed but the local service is not responding.
Start Ollama first, then re-run this script.
EOF
  exit 1
fi

if ! ollama list | awk '{print $1}' | tail -n +2 | grep -Fxq "${OLLAMA_MODEL}"; then
  log "Pulling Ollama model ${OLLAMA_MODEL}"
  ollama pull "${OLLAMA_MODEL}"
else
  log "Ollama model ${OLLAMA_MODEL} already installed"
fi

if [[ ! -d "${WHISPER_DIR}/.git" ]]; then
  log "Cloning whisper.cpp into ${WHISPER_DIR}"
  mkdir -p "$(dirname "${WHISPER_DIR}")"
  git clone https://github.com/ggml-org/whisper.cpp.git "${WHISPER_DIR}"
else
  log "Updating whisper.cpp checkout"
  git -C "${WHISPER_DIR}" pull --ff-only
fi

log "Building whisper.cpp"
cmake -S "${WHISPER_DIR}" -B "${WHISPER_DIR}/build"
cmake --build "${WHISPER_DIR}/build" -j

if [[ ! -f "${WHISPER_MODEL_PATH}" ]]; then
  log "Downloading whisper.cpp model ${WHISPER_MODEL_NAME}"
  (cd "${WHISPER_DIR}" && ./models/download-ggml-model.sh "${WHISPER_MODEL_NAME}")
else
  log "Whisper model ${WHISPER_MODEL_NAME} already present"
fi

if [[ ! -x "${WHISPER_BIN_PATH}" ]]; then
  echo "whisper-cli was not built successfully at ${WHISPER_BIN_PATH}" >&2
  exit 1
fi

log "Local setup is ready"
cat <<EOF

Add these settings to your .env before running the app:

BACKEND_PROVIDER="ollama"
MODEL_NAME="${OLLAMA_MODEL}"
OLLAMA_BASE_URL="http://localhost:11434/v1/"
WHISPER_CPP_BIN="${WHISPER_BIN_PATH}"
WHISPER_CPP_MODEL="${WHISPER_MODEL_PATH}"
LOCAL_TTS_VOICE="Samantha"

Recommended first run:
  reachy-mini-conversation-app --gradio --no-camera

Then enable the camera once the local voice loop is working:
  reachy-mini-conversation-app --gradio

EOF
